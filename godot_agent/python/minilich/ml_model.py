# -*- coding: utf-8 -*-
"""Крошечный трансформер mini-lich на чистом numpy (без PyTorch/llama.cpp).

Архитектура — decoder-only, та же семья, что у больших LLM, только на порядки
меньше: эмбеддинги -> N блоков (LayerNorm -> причинное многоголовое внимание
-> LayerNorm -> MLP) -> LayerNorm -> проекция в словарь.

Обучение: предсказание следующего токена (cross-entropy) с маской потерь —
учится ТОЛЬКО зона ответа (<fix>...<eos>), вход-условие не штрафуется.
Формат последовательности заранее закладывает канал размышлений
(<think>...</think>) — с v58 это не свободный CoT (модель на 300k параметров не
способна на абстрактные рассуждения), а детерминированный план фиксированного
вида (см. ml_fix.think_plan_text), который модель учится генерировать сама перед починкой.

Весь backprop написан вручную. Вес модели по умолчанию ~300k параметров
(~1.2 МБ float32 на диске) — «нейросеть-поддержка», а не главный программист.
С v58 генерация также поддерживает простейший repetition penalty на шаге argmax —
без него декодер-only микро-модели легко уходят в цикл повтора.
"""
import io
import json
import os

import numpy as np


def default_config(vocab):
    return {
        "vocab": int(vocab),
        "d_model": 96,
        "n_layers": 2,
        "n_heads": 4,
        "d_ff": 192,
        "n_ctx": 512,
    }


def _ln_forward(x, g, b, eps=1e-5):
    mu = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    inv = 1.0 / np.sqrt(var + eps)
    y = (x - mu) * inv
    return y * g + b, (y, inv, g)


def _ln_backward(dy, cache):
    y, inv, g = cache
    dyg = dy * g
    dg = (dy * y).sum(axis=0)
    db = dy.sum(axis=0)
    dx = inv * (dyg - dyg.mean(axis=-1, keepdims=True) - y * (dyg * y).mean(axis=-1, keepdims=True))
    return dx, dg, db


class TinyTransformer:
    def __init__(self, config, seed=0):
        self.cfg = dict(config)
        V = self.cfg["vocab"]
        d = self.cfg["d_model"]
        L = self.cfg["n_layers"]
        F = self.cfg["d_ff"]
        C = self.cfg["n_ctx"]
        rng = np.random.default_rng(seed)

        def w(*shape):
            return (rng.standard_normal(shape) * 0.02).astype(np.float32)

        p = {
            "tok": w(V, d),
            "pos": w(C, d),
            "lnf_g": np.ones(d, dtype=np.float32),
            "lnf_b": np.zeros(d, dtype=np.float32),
            "head": w(d, V),
        }
        for i in range(L):
            p[f"l{i}_ln1_g"] = np.ones(d, dtype=np.float32)
            p[f"l{i}_ln1_b"] = np.zeros(d, dtype=np.float32)
            p[f"l{i}_wq"] = w(d, d)
            p[f"l{i}_wk"] = w(d, d)
            p[f"l{i}_wv"] = w(d, d)
            p[f"l{i}_wo"] = w(d, d)
            p[f"l{i}_ln2_g"] = np.ones(d, dtype=np.float32)
            p[f"l{i}_ln2_b"] = np.zeros(d, dtype=np.float32)
            p[f"l{i}_w1"] = w(d, F)
            p[f"l{i}_b1"] = np.zeros(F, dtype=np.float32)
            p[f"l{i}_w2"] = w(F, d)
            p[f"l{i}_b2"] = np.zeros(d, dtype=np.float32)
        self.p = p
        self.opt = {k: {"m": np.zeros_like(v), "v": np.zeros_like(v)} for k, v in p.items()}
        self.step = 0

    # ------------------------------------------------------------------
    def param_count(self):
        return int(sum(v.size for v in self.p.values()))

    # ------------------------------------------------------------------
    def forward(self, ids):
        """ids: 1D массив длиной T <= n_ctx. Возвращает (logits, cache)."""
        cfg = self.cfg
        p = self.p
        T = len(ids)
        H = cfg["n_heads"]
        d = cfg["d_model"]
        dh = d // H
        x = p["tok"][ids] + p["pos"][:T]
        mask = np.triu(np.full((T, T), -1e9, dtype=np.float32), k=1)
        caches = []
        for i in range(cfg["n_layers"]):
            x_in = x
            a, ln1c = _ln_forward(x, p[f"l{i}_ln1_g"], p[f"l{i}_ln1_b"])
            q = (a @ p[f"l{i}_wq"]).reshape(T, H, dh).transpose(1, 0, 2)
            k = (a @ p[f"l{i}_wk"]).reshape(T, H, dh).transpose(1, 0, 2)
            v = (a @ p[f"l{i}_wv"]).reshape(T, H, dh).transpose(1, 0, 2)
            scores = q @ k.transpose(0, 2, 1) / np.sqrt(dh) + mask
            scores -= scores.max(axis=-1, keepdims=True)
            att = np.exp(scores)
            att /= att.sum(axis=-1, keepdims=True)
            o_heads = att @ v  # (H, T, dh)
            o_cat = o_heads.transpose(1, 0, 2).reshape(T, d)
            x = x_in + o_cat @ p[f"l{i}_wo"]
            x_mid = x
            a2, ln2c = _ln_forward(x, p[f"l{i}_ln2_g"], p[f"l{i}_ln2_b"])
            h_pre = a2 @ p[f"l{i}_w1"] + p[f"l{i}_b1"]
            h = np.maximum(h_pre, 0.0)
            x = x_mid + h @ p[f"l{i}_w2"] + p[f"l{i}_b2"]
            caches.append({
                "x_in": x_in, "a": a, "ln1c": ln1c, "q": q, "k": k, "v": v,
                "att": att, "o_cat": o_cat, "x_mid": x_mid, "a2": a2,
                "ln2c": ln2c, "h_pre": h_pre, "h": h,
            })
        xf, lnfc = _ln_forward(x, p["lnf_g"], p["lnf_b"])
        logits = xf @ p["head"]
        cache = {"ids": np.asarray(ids), "caches": caches, "xf": xf, "lnfc": lnfc, "T": T}
        return logits, cache

    # ------------------------------------------------------------------
    def loss_and_grads(self, ids, targets, loss_mask):
        """Один пример (T,): возвращает (loss, grads dict).
        targets[t] — правильный следующий токен для позиции t;
        loss_mask[t] = 1.0 только там, где мы учим модель (зона ответа)."""
        cfg = self.cfg
        p = self.p
        logits, cache = self.forward(ids)
        T = cache["T"]
        H = cfg["n_heads"]
        d = cfg["d_model"]
        dh = d // H
        m = np.asarray(loss_mask, dtype=np.float32)
        denom = max(float(m.sum()), 1.0)
        z = logits - logits.max(axis=-1, keepdims=True)
        ez = np.exp(z)
        probs = ez / ez.sum(axis=-1, keepdims=True)
        idx = np.arange(T)
        tgt = np.asarray(targets)
        loss = float((-np.log(probs[idx, tgt] + 1e-9) * m).sum() / denom)
        dlogits = probs.copy()
        dlogits[idx, tgt] -= 1.0
        dlogits *= (m / denom)[:, None]

        g = {k: np.zeros_like(v) for k, v in p.items()}
        xf = cache["xf"]
        g["head"] = xf.T @ dlogits
        dxf = dlogits @ p["head"].T
        dx, dgf, dbf = _ln_backward(dxf, cache["lnfc"])
        g["lnf_g"] = dgf
        g["lnf_b"] = dbf
        for i in reversed(range(cfg["n_layers"])):
            c = cache["caches"][i]
            # MLP: x = x_mid + relu(a2@w1+b1)@w2 + b2
            dh_out = dx  # градиент на выход блока
            g[f"l{i}_b2"] += dh_out.sum(axis=0)
            g[f"l{i}_w2"] += c["h"].T @ dh_out
            dh_relu = dh_out @ p[f"l{i}_w2"].T
            dh_pre = dh_relu * (c["h_pre"] > 0)
            g[f"l{i}_w1"] += c["a2"].T @ dh_pre
            g[f"l{i}_b1"] += dh_pre.sum(axis=0)
            da2 = dh_pre @ p[f"l{i}_w1"].T
            dx_mid_ln, dg2, db2 = _ln_backward(da2, c["ln2c"])
            g[f"l{i}_ln2_g"] += dg2
            g[f"l{i}_ln2_b"] += db2
            dx_mid = dh_out + dx_mid_ln  # residual
            # attention: x_mid = x_in + o_cat @ wo
            g[f"l{i}_wo"] += c["o_cat"].T @ dx_mid
            do_cat = dx_mid @ p[f"l{i}_wo"].T
            do_heads = do_cat.reshape(-1, H, dh).transpose(1, 0, 2)  # (H,T,dh)
            datt = do_heads @ c["v"].transpose(0, 2, 1)  # (H,T,T)
            dv = c["att"].transpose(0, 2, 1) @ do_heads  # (H,T,dh)
            att = c["att"]
            dscores = att * (datt - (datt * att).sum(axis=-1, keepdims=True))
            dscores /= np.sqrt(dh)
            dq = dscores @ c["k"]  # (H,T,dh)
            dk = dscores.transpose(0, 2, 1) @ c["q"]  # (H,T,dh)
            dq_f = dq.transpose(1, 0, 2).reshape(-1, d)
            dk_f = dk.transpose(1, 0, 2).reshape(-1, d)
            dv_f = dv.transpose(1, 0, 2).reshape(-1, d)
            a = c["a"]
            g[f"l{i}_wq"] += a.T @ dq_f
            g[f"l{i}_wk"] += a.T @ dk_f
            g[f"l{i}_wv"] += a.T @ dv_f
            da = dq_f @ p[f"l{i}_wq"].T + dk_f @ p[f"l{i}_wk"].T + dv_f @ p[f"l{i}_wv"].T
            dx_in_ln, dg1, db1 = _ln_backward(da, c["ln1c"])
            g[f"l{i}_ln1_g"] += dg1
            g[f"l{i}_ln1_b"] += db1
            dx = dx_mid + dx_in_ln  # residual
        # эмбеддинги
        T_len = cache["T"]
        g["pos"][:T_len] += dx
        np.add.at(g["tok"], cache["ids"], dx)
        return loss, g

    # ------------------------------------------------------------------
    def adam_step(self, grads, lr=1e-3, beta1=0.9, beta2=0.999, eps=1e-8):
        self.step += 1
        t = self.step
        for k, v in self.p.items():
            gk = grads[k]
            st = self.opt[k]
            st["m"] = beta1 * st["m"] + (1 - beta1) * gk
            st["v"] = beta2 * st["v"] + (1 - beta2) * (gk * gk)
            mhat = st["m"] / (1 - beta1 ** t)
            vhat = st["v"] / (1 - beta2 ** t)
            v -= (lr * mhat / (np.sqrt(vhat) + eps)).astype(np.float32)

    # ------------------------------------------------------------------
    def generate(self, prompt_ids, max_new=256, eos_id=None, repetition_penalty=1.0, repetition_window=32):
        """Жадная генерация. Возвращает ТОЛьКО новые токены (без промпта).

        repetition_penalty > 1.0 включает штраф за повторение (Gemini review, v58):
        прямо перед argmax логиты токенов, встретившихся в последних
        repetition_window токенах, делятся (если позитивный) или умножаются
        (если отрицательный) на этот коэффициент — стоит микросекунды,
        но хорошо рвёт циклы. При repetition_penalty == 1.0 поведение тождественно
        обычному жадному декодированию (ничего не меняется).
        """
        C = self.cfg["n_ctx"]
        ids = list(prompt_ids)[-C:]
        out = []
        for _ in range(max_new):
            logits, _ = self.forward(np.asarray(ids[-C:], dtype=np.int64))
            step_logits = logits[-1]
            if repetition_penalty and repetition_penalty != 1.0 and repetition_window > 0:
                step_logits = step_logits.copy()
                recent = set(int(x) for x in ids[-repetition_window:])
                for tid in recent:
                    if 0 <= tid < step_logits.shape[0]:
                        if step_logits[tid] > 0:
                            step_logits[tid] /= repetition_penalty
                        else:
                            step_logits[tid] *= repetition_penalty
            nxt = int(np.argmax(step_logits))
            if eos_id is not None and nxt == eos_id:
                break
            out.append(nxt)
            ids.append(nxt)
        return out

    # ------------------------------------------------------------------
    def save(self, path):
        """Атомарное сохранение (tmp + rename): отключение ПК во время записи
        не оставит битый файл поверх рабочего чекпоинта."""
        payload = {"__config__": np.frombuffer(json.dumps(self.cfg).encode("utf-8"), dtype=np.uint8),
                   "__step__": np.asarray([self.step], dtype=np.int64)}
        for k, v in self.p.items():
            payload["p_" + k] = v
        for k, st in self.opt.items():
            payload["m_" + k] = st["m"]
            payload["v_" + k] = st["v"]
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            np.savez(f, **payload)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as z:
            cfg = json.loads(bytes(z["__config__"]).decode("utf-8"))
            model = cls(cfg)
            model.step = int(z["__step__"][0])
            for k in model.p:
                model.p[k] = z["p_" + k].astype(np.float32)
                model.opt[k]["m"] = z["m_" + k].astype(np.float32)
                model.opt[k]["v"] = z["v_" + k].astype(np.float32)
        return model

import pytest

from python.kernel.errors import AppError
from ..domain import render
from ..domain.inventory import file_inventory
from .plan_corpus import named, source


def test_auto_virtual_filter_and_source_group_order():
    info = file_inventory(source(named('virtuals_auto')))
    assert render.suggest_groups(info, 'donor', 1100) == [{'module': 'donor_part1', 'funcs': ['alpha']}]


@pytest.mark.parametrize('module', ['part_one', 'part_two'])
def test_empty_funcs_exact_native_message(module):
    with pytest.raises(AppError) as exc:
        render.normalize_groups([{'module': module, 'funcs': []}], {'alpha': {}})
    assert exc.value.kind == 'invalid_input'
    assert exc.value.message == 'группа %s: пустой список funcs' % module


def test_rewrite_paths_members_locals_modulo_and_unknowns():
    context = {'funcs': {'other'}, 'vars': {'state'}, 'copies': {'LIMIT'},
               'methods': {'get_tree'}, 'props': {'visible'}, 'params': ['param']}
    body = '\tvar local = state\n\tother(self, $Child, $"A/B", %Unique)\n\treturn param + LIMIT + get_tree() + visible + mystery + 5 % 2\n'
    rewritten, unknown = render.rewrite_body(body, context)
    assert rewritten == '\tvar local = panel.state\n\tpanel.other(panel, panel.get_node("Child"), panel.get_node("A/B"), panel.get_node("%Unique"))\n\treturn param + LIMIT + panel.get_tree() + panel.visible + mystery + 5 % 2\n'
    assert unknown == {'mystery'}


def test_inference_taint_transitive_and_unrelated_constant():
    body = 'var one := panel.get_tree()\nvar two := one\nvar three := [two]\nvar safe := 1\n'
    assert render.downgrade_panel_inference(body) == 'var one = panel.get_tree()\nvar two = one\nvar three = [two]\nvar safe := 1\n'


def test_native_overlapping_edits_are_skipped():
    assert render.apply_edits('abcdef', [(1, 3, 'X'), (2, 4, 'Y'), (4, 5, 'Z')]) == 'aXdZf'


def test_wrapper_preserves_await_signature_and_static_quirk():
    info = file_inventory(source(named('private_static_await')))
    funcs = {f['name']: f for f in info['funcs']}
    assert render.render_wrapper(funcs['beta'], 'PartOne')[-1] == '\tawait PartOne.beta(self)'
    assert render.render_static_sig(funcs['gamma'])[0].startswith('static static func gamma(panel, ')

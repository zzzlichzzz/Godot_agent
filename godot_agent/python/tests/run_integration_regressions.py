"""Run offline integration suites in separate processes, then optional real Godot tests."""
import argparse
from pathlib import Path
import re
import subprocess
import sys


SUITES = """
test_editor_context test_gather_context test_semantic_index
test_rename_symbol test_rename_symbol_flow test_file_refactor test_file_refactor_flow test_node_refactor test_node_refactor_flow test_client_refactor_flow test_scene_actions test_scene_action_flow
test_project_settings_actions test_project_settings_flow test_godot_headless_validation
test_transaction_actions test_transaction_flow test_high_level_actions test_high_level_flow
test_resource_actions test_resource_action_flow test_runtime_debug test_runtime_debug_flow
test_runtime_checks test_runtime_check_flow test_runtime_result_http test_answer_judge
test_gdscript_wiring test_chat_pending_cleanup test_rollback_by_entry test_tree_excludes_addon
test_pyinstaller_spec test_api_end_to_end test_megaprompt_once test_qwen_no_double_send
test_server_auth test_http_boundary_safety test_history_journal_safety test_write_recovery_safety
test_api_history test_api_history_failures test_api_backend test_api_route_persistence
test_path_policy_safety test_move_safety test_chat_state_isolation test_chat_site_restore
test_api_routes test_v87_9_regen test_v88_6_qwen_net test_deepseek_no_double_send
test_v105_attachment_note test_paste_attachment test_librarian
test_api_transport test_api_secrets_and_limits test_anthropic_compat
test_catalog test_provider_catalog test_doh
test_net_monitor_lifecycle test_browser_wait_safety test_browser_turn_cancel
test_browser_send_acceptance test_aistudio_send_acceptance
test_browser_target_binding test_v88_11_live_input test_v105_spoof_per_site
test_v88_16_paste_fix test_v88_12_net_confirm test_v88_7_input_wait
test_v88_8_net_first test_rate_limit_sleep test_v87_1_kimi_cdp
test_v88_0_aistudio test_v105_net_answer_ready test_arena_parser test_v88_13_multi_action
""".split()


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", help="Run isolated live tests using this Godot executable")
    args = parser.parse_args()
    python_root = Path(__file__).resolve().parent.parent
    suites = list(SUITES)
    live = ["test_godot_live", "test_godot_executor_live", "test_runtime_ownership_live",
            "test_headless_validator_live", "test_file_refactor_live", "test_node_refactor_live"]
    if args.godot:
        suites.extend(live)
    failures = []
    for name in suites:
        command = [sys.executable, "-B", "-X", "utf8", str(python_root / "tests" / (name + ".py"))]
        if name in live:
            command += ["--godot", str(Path(args.godot).resolve())]
        try:
            result = subprocess.run(command, cwd=python_root, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=300)
            output = result.stdout + result.stderr
            passed = result.returncode == 0
        except subprocess.TimeoutExpired:
            output = "Timed out after 300 seconds"
            passed = False
        print(("PASS " if passed else "FAIL ") + name, flush=True)
        skipped = re.findall(r"OK \(skipped=\d+\)", output)
        skipped.extend(re.findall(r"^SKIP .*", output, re.MULTILINE))
        if skipped:
            print("  " + ", ".join(skipped))
        if not passed or name in live:
            print(output)
        if not passed:
            failures.append(name)
    print("RESULT: %d/%d suites passed" % (len(suites) - len(failures), len(suites)))
    if not args.godot:
        print("Live engine checks NOT run; pass --godot to include them.")
    if failures:
        print("FAILED: " + ", ".join(failures))
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())

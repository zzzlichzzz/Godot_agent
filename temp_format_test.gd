
extends SceneTree
func _init():
    var s = 'safe_post_move_sync_success'
    var res = s % ['a', 'b', 1, 2]
    print('RESULT:', res)
    quit()

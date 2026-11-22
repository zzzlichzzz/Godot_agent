extends EditorPlugin

# Ссылка в закрытом аддоне: индекс её не видит, план её не трогает.

func pokes(hero) -> void:
	hero.take_damage(1)

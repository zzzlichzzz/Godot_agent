extends RefCounted

func describe(path: String) -> String:
	print("plain")
	print("with \"escape\"")
	print('single')
	return """
multi
line"""

var broken := "no end

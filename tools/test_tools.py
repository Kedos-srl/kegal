def greet(**kwargs):
    name = kwargs.get('name', 'User')
    greeting = kwargs.get('greeting', 'Hello')
    return f"{greeting}, {name}!"


def add_numbers(**kwargs):
    a = kwargs.get('a', 0)
    b = kwargs.get('b', 0)
    return a + b



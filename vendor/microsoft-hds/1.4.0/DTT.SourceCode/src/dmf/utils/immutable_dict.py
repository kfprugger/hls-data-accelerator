class ImmutableDict(dict):
    def __readonly(self, *args, **kwargs):
        raise TypeError('This dictionary is immutable.')

    __setitem__ = __readonly
    __delitem__ = __readonly
    clear = __readonly
    pop = __readonly
    popitem = __readonly
    setdefault = __readonly
    update = __readonly

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __hash__(self):
        # Use the hash of the frozenset of items.
        # Since dictionary items are pairs (key, value), and both keys and values can be hashed,
        # this provides a consistent hash for the entire dictionary.
        return hash(frozenset(self.items()))

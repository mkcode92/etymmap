import os
import pickle


def cached(f, file, refresh=False):
    if os.path.isfile(file) and not refresh:
        with open(file, "rb") as src:
            obj = pickle.load(src)
    else:
        with open(file, "wb") as dest:
            obj = f()
            pickle.dump(obj, dest)
    return obj

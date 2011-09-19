class Query(dict):

    def __init__(self, model_class):
        self._model_cls = model_class

    def filter(self, property_operator, value):
        raise NotImplementedError

    def order(self, property):
        raise NotImplementedError

    def ancestor(self, ancestor):
        raise NotImplementedError

    def get(self):
        raise NotImplementedError

    def fetch(self, limit, offset=0):
        raise NotImplementedError

    def count(self, limit):
        raise NotImplementedError


# Copied from google.appengine.api.datastore.
# Used in ext.gql.GQL


def _AddOrAppend(dictionary, key, value):
    """Adds the value to the existing values in the dictionary, if any.

    If dictionary[key] doesn't exist, sets dictionary[key] to value.

    If dictionary[key] is not a list, sets dictionary[key]
    to [old_value, value].

    If dictionary[key] is a list, appends value to that list.

    Args:
      dictionary: a dict
      key, value: anything
  """
    if key in dictionary:
        existing_value = dictionary[key]
        if isinstance(existing_value, list):
            existing_value.append(value)
        else:
            dictionary[key] = [existing_value, value]
    else:
        dictionary[key] = value

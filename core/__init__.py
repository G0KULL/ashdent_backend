from rest_framework.utils.encoders import JSONEncoder
from bson import ObjectId

original_default = JSONEncoder.default

def custom_default(self, obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    return original_default(self, obj)

JSONEncoder.default = custom_default

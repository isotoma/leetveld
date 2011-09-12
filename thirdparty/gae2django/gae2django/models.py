from django.db import models

from gaeapi.appengine.ext import db


class RefTestModel(db.Model):
    value = db.StringProperty()


class RegressionTestModel(db.Model):
    xstring = db.StringProperty()
    xlist = db.ListProperty(str)
    xuser = db.UserProperty(auto_current_user_add=True)
    ref = db.ReferenceProperty(RefTestModel)
    blob = db.BlobProperty()

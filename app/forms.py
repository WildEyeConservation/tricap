# D Joubert Innoventix Consulting 14 November 2016
# Forms for the GUI

from flask_wtf import Form
from wtforms import StringField, SelectField, SubmitField, FieldList


class SettingsForm(Form):
    """The form for the settings page. Contains the three buttons (test, save and revert) and
    then two FieldLists that must be expanded with the settings read from the config file."""
    string_settings = FieldList(StringField(), min_entries=0)
    select_settings = FieldList(SelectField(), min_entries=0)
    test = SubmitField(label='Test')
    save = SubmitField(label='Save')
    revert = SubmitField(label='Revert')

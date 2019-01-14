# -*- coding: utf-8 -*-
"""
web2ldap.app.addmodifyform: input form for adding and modifying an entry

web2ldap - a web-based LDAP Client,
see https://www.web2ldap.de for details

(c) 1998-2019 by Michael Stroeder <michael@stroeder.com>

This software is distributed under the terms of the
Apache License Version 2.0 (Apache-2.0)
https://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import absolute_import

from cStringIO import StringIO

import ldap0
import ldap0.ldif
import ldap0.schema
from ldap0.schema.models import \
    AttributeType, \
    ObjectClass, \
    DITStructureRule,  \
    DITContentRule

import web2ldapcnf

import web2ldap.web
from web2ldap.web import escape_html
import web2ldap.ldapsession
import web2ldap.app.core
import web2ldap.app.cnf
import web2ldap.app.form
import web2ldap.app.gui
import web2ldap.app.read
import web2ldap.app.modify
import web2ldap.app.schema
from web2ldap.app.schema.viewer import display_nameoroid_list
from web2ldap.app.schema.syntaxes import syntax_registry
from web2ldap.msbase import GrabKeys


H1_MSG = {
    'add':'Add new entry',
    'modify':'Modify entry',
}

INPUT_FORM_BEGIN_TMPL = """

  <h1>{text_heading}</h1>

  {text_msg}

  {text_supentry}

  {form_begin}

  {field_dn}
  {field_currentformtype}

  <input
    type="submit"
    value="{text_submit}"
    title="{text_submit} the entry with your input"
  >

  Change input form:

  <button
    type="submit"
    name="in_ft"
    value="Template"
    title="Switch to HTML template input form"
  >
    Template
  </button>

  <button
    type="submit"
    name="in_ft"
    value="Table"
    title="Switch to attribute table input form"
  >
    Table
  </button>

  <button
    type="submit"
    name="in_ft"
    value="LDIF"
    title="Switch to multi-line LDIF input form"
  >
    LDIF
  </button>

  Change&nbsp;Object&nbsp;
  <button
    type="submit"
    name="in_ft"
    title="Switch to object class select form"
    value="OC">
    Classes
  </button>
"""

INPUT_FORM_LDIF_TMPL = """
<fieldset>
  <legend>Raw LDIF data</legend>
  <textarea name="in_ldif" rows="50" cols="80" wrap="off">{value_ldif}</textarea>
  <p>
    Notes:
  </p>
  <ul>
    <li>Lines containing "dn:" will be ignored</li>
    <li>Only the first entry (until first empty line) will be accepted</li>
    <li>Maximum length is set to {value_ldifmaxbytes} bytes</li>
    <li>Allowed URL schemes: {text_ldifurlschemes}</li>
  </ul>
</fieldset>
"""


class InputFormEntry(web2ldap.app.read.DisplayEntry):

    def __init__(
            self, app, dn, schema, entry,
            writeable_attr_oids,
            existing_object_classes=None,
            invalid_attrs=None
        ):
        assert isinstance(dn, unicode), TypeError("Argument 'dn' must be unicode, was %r" % (dn))
        web2ldap.app.read.DisplayEntry.__init__(
            self, app, dn, schema, entry, 'fieldSep', False
        )
        self.existing_object_classes = existing_object_classes
        self.relax_rules_enabled = self._app.ls.l._get_server_ctrls('**write**').has_key(web2ldap.ldapsession.CONTROL_RELAXRULES)
        self.manage_dsait_enabled = self._app.ls.l._get_server_ctrls('**all**').has_key(web2ldap.ldapsession.CONTROL_MANAGEDSAIT)
        self.writeable_attr_oids = writeable_attr_oids
        self.invalid_attrs = invalid_attrs or {}
        new_object_classes = set(list(self.entry.object_class_oid_set())) - set([
            self.entry._s.getoid(ObjectClass, oc_name)
            for oc_name in existing_object_classes or []
        ])
        new_attribute_types = self.entry._s.attribute_types(
            new_object_classes,
            raise_keyerror=0,
            ignore_dit_content_rule=self.relax_rules_enabled
        )
        old_attribute_types = self.entry._s.attribute_types(
            existing_object_classes or [],
            raise_keyerror=0,
            ignore_dit_content_rule=self.relax_rules_enabled
        )
        self.new_attribute_types_oids = set()
        self.new_attribute_types_oids.update(new_attribute_types[0].keys())
        self.new_attribute_types_oids.update(new_attribute_types[1].keys())
        for at_oid in old_attribute_types[0].keys()+old_attribute_types[1].keys():
            try:
                self.new_attribute_types_oids.remove(at_oid)
            except KeyError:
                pass

    def _reset_input_counters(self):
        self.attr_counter = 0
        self.row_counter = 0
        return # _reset_input_counters()

    def __getitem__(self, nameoroid):
        """
        Return HTML input field(s) for the attribute specified by nameoroid.
        """
        oid = self.entry._at2key(nameoroid)[0]
        nameoroid_se = self.entry._s.get_obj(AttributeType, nameoroid)
        syntax_class = web2ldap.app.schema.syntaxes.syntax_registry.get_syntax(
            self.entry._s,
            nameoroid,
            self.soc,
        )
        try:
            attr_values = self.entry.__getitem__(nameoroid)
        except KeyError:
            attr_values = []
        # Attribute value list must contain at least one element to display an input field
        attr_values = attr_values or [None]

        result = []

        # Eliminate binary attribute values from input form
        if not syntax_class.editable:
            attr_values = ['']

        attr_inst = syntax_class(
            self._app, self.dn, self.entry._s, nameoroid, None, self.entry
        )
        invalid_attr_indexes = set(self.invalid_attrs.get(nameoroid, []))

        for attr_index, attr_value in enumerate(attr_values):

            attr_inst = syntax_class(
                self._app, self.dn, self.entry._s, nameoroid, attr_value, self.entry,
            )
            highlight_invalid = attr_index in invalid_attr_indexes

            if (
                    # Attribute type 'objectClass' always read-only here
                    oid == '2.5.4.0'
                ) or (
                    # Attribute type 'structuralObjectClass' always read-only no matter what
                    oid == '2.5.21.9'
                ) or (
                    # Check whether the server indicated this attribute not to be writeable by bound identity
                    not self.writeable_attr_oids is None and \
                    not oid in self.writeable_attr_oids and \
                    not oid in self.new_attribute_types_oids
                ) or (
                    # Check whether attribute type/value is used in the RDN => not writeable
                    self.existing_object_classes and \
                    attr_value and \
                    self.rdn_dict.has_key(nameoroid) and \
                    self.rdn_dict[nameoroid].has_key(attr_value)
                ) or (
                    # Set to writeable if relax rules control is in effect and attribute is NO-USER-APP in subschema
                    not self.relax_rules_enabled and \
                    web2ldap.app.schema.no_userapp_attr(self.entry._s, oid)
                ):
                result.append('\n'.join((
                    '<span class="InvalidInput">'*highlight_invalid,
                    self._app.form.hiddenFieldHTML('in_at', nameoroid.decode('ascii'), u''),
                    web2ldap.app.gui.HIDDEN_FIELD % ('in_avi', str(self.attr_counter), ''),
                    web2ldap.app.gui.HIDDEN_FIELD % (
                        'in_av',
                        self._app.form.utf2display(attr_inst.formValue(), sp_entity='  '),
                        self._app.form.utf2display(attr_inst.formValue(), sp_entity='&nbsp;&nbsp;')
                    ),
                    attr_inst.valueButton(self._app.command, self.row_counter, '+'),
                    '</span>'*highlight_invalid,
                )))
                self.row_counter += 1

            else:
                attr_title = u''
                attr_type_tags = []
                attr_type_name = unicode(nameoroid).split(';')[0]
                if nameoroid_se:
                    attr_type_name = (nameoroid_se.names or [nameoroid_se.oid])[0].decode(self._app.ls.charset)
                    try:
                        attr_title = (nameoroid_se.desc or '').decode(self._app.ls.charset)
                    except UnicodeError:
                        # This happens sometimes because of wrongly encoded schema files
                        attr_title = u''
                    # Determine whether transfer syntax has to be specified with ;binary
                    if (
                            nameoroid.endswith(';binary') or
                            oid in web2ldap.app.schema.NEEDS_BINARY_TAG or
                            nameoroid_se.syntax in web2ldap.app.schema.NEEDS_BINARY_TAG
                        ):
                        attr_type_tags.append('binary')
                input_fields = attr_inst.formFields()
                for input_field in input_fields:
                    input_field.name = 'in_av'
                    input_field.charset = self._app.form.accept_charset
                    result.append('\n'.join([
                        '<span class="InvalidInput">'*highlight_invalid,
                        web2ldap.app.gui.HIDDEN_FIELD % (
                            'in_at',
                            ';'.join([attr_type_name.encode('ascii')]+attr_type_tags),
                            ''
                        ),

                        web2ldap.app.gui.HIDDEN_FIELD % ('in_avi', str(self.attr_counter), ''),
                        input_field.inputHTML(
                            id_value=u'_'.join((
                                u'inputattr', attr_type_name, unicode(attr_index)
                            )).encode(self._app.form.accept_charset),
                            title=attr_title
                        ),
                        attr_inst.valueButton(self._app.command, self.row_counter, '+'),
                        attr_inst.valueButton(self._app.command, self.row_counter, '-'),
                        '</span>'*highlight_invalid,
                    ]))
                    self.row_counter += 1

            self.attr_counter += 1

        return '<a class="hide" id="in_a_%s"></a>%s' % (
            self._app.form.utf2display(nameoroid.decode('ascii')),
            '\n<br>\n'.join(result),
        )

    def attribute_types(self):
        # Initialize a list of assertions for filtering attribute types
        # displayed in the input form
        attr_type_filter = [
            ('no_user_mod', [0]),
            #('usage', range(2)),
            ('collective', [0]),
        ]
        # Check whether Manage DIT control is in effect,
        # filter out OBSOLETE attribute types otherwise
        relax_rules_enabled = self._app.ls.l._get_server_ctrls('**write**').has_key(web2ldap.ldapsession.CONTROL_RELAXRULES)
        if not relax_rules_enabled:
            attr_type_filter.append(('obsolete', [0]))

        # Filter out extensibleObject
        object_class_oids = self.entry.object_class_oid_set()
        try:
            object_class_oids.remove('1.3.6.1.4.1.1466.101.120.111')
        except KeyError:
            pass
        try:
            object_class_oids.remove('extensibleObject')
        except KeyError:
            pass

        required_attrs_dict, allowed_attrs_dict = self.entry._s.attribute_types(
            list(object_class_oids),
            attr_type_filter=attr_type_filter,
            raise_keyerror=0,
            ignore_dit_content_rule=relax_rules_enabled
        )

        # Additional check whether to explicitly add object class attribute.
        # This is a work-around for LDAP servers which mark the
        # objectClass attribute as not modifiable (e.g. MS Active Directory)
        if not required_attrs_dict.has_key('2.5.4.0') and not allowed_attrs_dict.has_key('2.5.4.0'):
            required_attrs_dict['2.5.4.0'] = self.entry._s.get_obj(ObjectClass, '2.5.4.0')
        return required_attrs_dict, allowed_attrs_dict

    def fieldset_table(self, attr_types_dict, fieldset_title):
        self._app.outf.write(
            """<fieldset title="%s">
            <legend>%s</legend>
            <table summary="%s">
            """ % (fieldset_title, fieldset_title, fieldset_title)
        )
        seen_attr_type_oids = ldap0.cidict.cidict()
        attr_type_names = ldap0.cidict.cidict()
        for a in self.entry.keys():
            at_oid = self.entry._at2key(a)[0]
            if attr_types_dict.has_key(at_oid):
                seen_attr_type_oids[at_oid] = None
                attr_type_names[a.encode('ascii')] = None
        for at_oid, at_se in attr_types_dict.items():
            if (
                    at_se and
                    not seen_attr_type_oids.has_key(at_oid) and
                    not web2ldap.app.schema.no_userapp_attr(self.entry._s, at_oid)
                ):
                attr_type_names[(at_se.names or (at_se.oid,))[0].encode('ascii')] = None
        attr_types = attr_type_names.keys()
        attr_types.sort(key=str.lower)
        for attr_type in attr_types:
            attr_type_name = web2ldap.app.gui.SchemaElementName(self._app, self.entry._s, attr_type, AttributeType)
            attr_value_field_html = self[attr_type]
            self._app.outf.write(
                '<tr>\n<td class="InputAttrType">\n%s\n</td>\n<td>\n%s\n</td>\n</tr>\n' % (
                    attr_type_name,
                    attr_value_field_html,
                )
            )
        self._app.outf.write('</table>\n</fieldset>\n')
        return # fieldset_table()

    def table_input(self, attrs_dict_list):
        self._reset_input_counters()
        for attr_dict, fieldset_title in attrs_dict_list:
            if attr_dict:
                self.fieldset_table(attr_dict, fieldset_title)
        return # table_input()

    def template_output(self, cnf_key, display_duplicate_attrs=True):
        self._reset_input_counters()
        displayed_attrs = web2ldap.app.read.DisplayEntry.template_output(
            self, cnf_key, display_duplicate_attrs=display_duplicate_attrs
        )
        # Output hidden fields for attributes not displayed in template-based input form
        for attr_type, attr_values in self.entry.items():
            at_oid = self.entry._at2key(attr_type)[0]
            syntax_class = syntax_registry.get_syntax(self.entry._s, attr_type, self.soc)
            if syntax_class.editable and \
               not web2ldap.app.schema.no_userapp_attr(self.entry._s, attr_type) and \
               not at_oid in displayed_attrs:
                for attr_value in attr_values:
                    attr_inst = syntax_class(
                        self._app, self.dn, self.entry._s, attr_type, attr_value, self.entry
                    )
                    self._app.outf.write(self._app.form.hiddenFieldHTML('in_at', attr_type.decode('ascii'), u''))
                    self._app.outf.write(web2ldap.app.gui.HIDDEN_FIELD % ('in_avi', str(self.attr_counter), ''))
                    try:
                        attr_value_html = self._app.form.utf2display(attr_inst.formValue(), sp_entity='  ')
                    except UnicodeDecodeError:
                        # Simply display an empty string if anything goes wrong with Unicode decoding (e.g. with binary attributes)
                        attr_value_html = ''
                    self._app.outf.write(web2ldap.app.gui.HIDDEN_FIELD % (
                        'in_av', attr_value_html, ''
                    ))
                    self.attr_counter += 1
        return displayed_attrs # template_output()

    def ldif_input(self):
        f = StringIO()
        ldif_writer = ldap0.ldif.LDIFWriter(f)
        ldap_entry = {}
        for attr_type in self.entry.keys():
            attr_values = self.entry.__getitem__(attr_type)
            if not web2ldap.app.schema.no_userapp_attr(self.entry._s, attr_type):
                ldap_entry[attr_type] = [
                    attr_value
                    for attr_value in attr_values
                    if attr_value
                ]
        ldif_writer.unparse(self.dn.encode(self._app.ls.charset), ldap_entry)
        self._app.outf.write(
            INPUT_FORM_LDIF_TMPL.format(
                value_ldif=self._app.form.utf2display(
                    f.getvalue().decode('utf-8'),
                    sp_entity='  ',
                    lf_entity='\n',
                ),
                value_ldifmaxbytes=web2ldapcnf.ldif_maxbytes,
                text_ldifurlschemes=', '.join(web2ldapcnf.ldif_url_schemes)
            )
        )
        return # ldif_input()


def SupentryDisplayString(app, parent_dn, schema, supentry_display_tmpl=None):
    supentry_display_tmpl = supentry_display_tmpl or \
        r"""
        <p title="Superior entry information">
          <strong>Superior entry:</strong><br>
          %s
        </p>
        """
    assert isinstance(parent_dn, unicode), TypeError("Argument 'parent_dn' must be unicode, was %r" % (parent_dn))
    if parent_dn is None:
        return ''
    supentry_display_strings = []
    inputform_supentrytemplate = web2ldap.app.cnf.GetParam(app.ls, 'inputform_supentrytemplate', {})
    if inputform_supentrytemplate:
        inputform_supentrytemplate_attrtypes = set(['objectClass'])
        for oc in inputform_supentrytemplate.keys():
            inputform_supentrytemplate_attrtypes.update(GrabKeys(inputform_supentrytemplate[oc]).keys)
        try:
            parent_search_result = app.ls.readEntry(
                parent_dn,
                attrtype_list=list(inputform_supentrytemplate_attrtypes),
            )
        except (
                ldap0.NO_SUCH_OBJECT,
                ldap0.INSUFFICIENT_ACCESS,
                ldap0.REFERRAL,
            ):
            pass
        else:
            if parent_search_result:
                parent_entry = web2ldap.app.read.DisplayEntry(
                    app, parent_dn, schema,
                    parent_search_result[0][1], 'readSep', 0
                )
                for oc in parent_search_result[0][1].get('objectClass', []):
                    try:
                        inputform_supentrytemplate[oc]
                    except KeyError:
                        pass
                    else:
                        supentry_display_strings.append(inputform_supentrytemplate[oc] % parent_entry)
    if supentry_display_strings:
        return supentry_display_tmpl % ('\n'.join(supentry_display_strings))
    return ''


def ObjectClassForm(
        app,
        sub_schema,
        existing_object_classes,
        structural_object_class
    ):
    """Form for choosing object class(es)"""

    def get_possible_soc(app, sub_schema, parent_dn):
        """
        This function tries to determine the possible structural object classes
        and returns it as a list of object class NAMEs
        """
        all_structural_oc = None
        dit_structure_rule_html = ''
        # Determine possible structural object classes based on DIT structure rules
        # and name forms if DIT structure rules are defined in subschema
        if sub_schema.sed[DITStructureRule]:
            dit_structure_ruleid = app.ls.getGoverningStructureRule(parent_dn, sub_schema)
            if dit_structure_ruleid is not None:
                subord_structural_ruleids, subord_structural_oc = sub_schema.get_subord_structural_oc_names(dit_structure_ruleid)
                if subord_structural_oc:
                    all_structural_oc = subord_structural_oc
                    dit_structure_rule_html = 'DIT structure rules:<br>%s' % ('<br>'.join(
                        display_nameoroid_list(
                            app,
                            sub_schema,
                            subord_structural_ruleids,
                            DITStructureRule
                        )
                    ))
        # Determine possible structural object classes based on operational
        # attribute 'allowedChildClasses' (MS AD or OpenLDAP with slapo-allowed)
        elif (
                '1.2.840.113556.1.4.912' in sub_schema.sed[AttributeType] and
                'OpenLDAProotDSE' not in app.ls.rootDSE.get('objectClass', [])
            ):
            try:
                parent_search_result = app.ls.readEntry(
                    parent_dn,
                    attrtype_list=['allowedChildClasses', 'allowedChildClassesEffective'],
                )
            except (
                    ldap0.NO_SUCH_OBJECT,
                    ldap0.INSUFFICIENT_ACCESS,
                    ldap0.REFERRAL,
                ):
                pass
            else:
                if parent_search_result:
                    parent_entry = parent_search_result[0][1]
                    try:
                        allowed_child_classes = parent_entry['allowedChildClasses']
                    except KeyError:
                        dit_structure_rule_html = ''
                    else:
                        allowed_child_classes_kind_dict = {0:[], 1:[], 2:[]}
                        for av in allowed_child_classes:
                            at_se = sub_schema.get_obj(ObjectClass, av)
                            if not at_se is None:
                                allowed_child_classes_kind_dict[at_se.kind].append(av)
                        all_structural_oc = allowed_child_classes_kind_dict[0]
                        #all_abstract_oc = allowed_child_classes_kind_dict[1]
                        #all_auxiliary_oc = allowed_child_classes_kind_dict[2]
                        dit_structure_rule_html = 'Governed by <var>allowedChildClasses</var>.'
        return all_structural_oc, dit_structure_rule_html # get_possible_soc()


    def ExpertOCFields(app, sub_schema, parent_dn):

        all_structural_oc, all_abstract_oc, all_auxiliary_oc = web2ldap.app.schema.object_class_categories(sub_schema, all_oc)
        dit_structure_rule_html = ''

        restricted_structural_oc, dit_structure_rule_html = get_possible_soc(app, sub_schema, parent_dn)
        all_structural_oc = restricted_structural_oc or all_structural_oc

        existing_misc_oc = set(existing_object_classes)
        for a in existing_structural_oc+existing_abstract_oc+existing_auxiliary_oc:
            existing_misc_oc.discard(a)
        existing_misc_oc = list(existing_misc_oc)

        dit_content_rule_html = ''
        # Try to look up a DIT content rule
        if existing_object_classes and structural_object_class:
            # Determine OID of structural object class
            soc_oid = sub_schema.name2oid[ObjectClass].get(structural_object_class, structural_object_class)
            dit_content_rule = sub_schema.get_obj(DITContentRule, soc_oid, None)
            if dit_content_rule is not None:
                if dit_content_rule.obsolete:
                    dit_content_rule_status_text = 'Ignored obsolete'
                elif relax_rules_enabled:
                    dit_content_rule_status_text = 'Ignored'
                else:
                    dit_content_rule_status_text = 'Governed by'
                    all_auxiliary_oc_oids = set([
                        sub_schema.getoid(ObjectClass, nameoroid)
                        for nameoroid in dit_content_rule.aux
                    ])
                    all_auxiliary_oc = [
                        oc
                        for oc in all_auxiliary_oc
                        if sub_schema.getoid(ObjectClass, oc) in all_auxiliary_oc_oids
                    ]
                dit_content_rule_html = '%s<br>DIT content rule:<br>%s' % (
                    dit_content_rule_status_text,
                    web2ldap.app.gui.SchemaElementName(app, sub_schema, dit_content_rule.names[0], DITContentRule)
                )

        abstract_select_field = web2ldap.app.form.ObjectClassSelect(
            name='in_oc',
            text='Abstract object class(es)',
            options=all_abstract_oc,
            default=existing_abstract_oc,
            size=20
        )
        structural_select_field = web2ldap.app.form.ObjectClassSelect(
            name='in_oc',
            text='Structural object class(es)',
            options=all_structural_oc,
            default=existing_structural_oc,
            size=20
        )
        auxiliary_select_field = web2ldap.app.form.ObjectClassSelect(
            name='in_oc',
            text='Auxiliary object class(es)',
            options=all_auxiliary_oc,
            default=existing_auxiliary_oc,
            size=20
        )
        misc_select_field = web2ldap.app.form.ObjectClassSelect(
            name='in_oc',
            text='Misc. object class(es)',
            options=[],
            default=existing_misc_oc,
            size=20
        )
        if existing_misc_oc:
            misc_select_field_th = '<th><label for="add_misc_oc">Misc.<label></th>'
            misc_select_field_td = '<td>%s</td>' % (misc_select_field.inputHTML(id_value='add_misc_oc'))
        else:
            misc_select_field_th = ''
            misc_select_field_td = ''

        input_currentformtype = app.form.getInputValue('in_oft', ['Template'])[0]

        add_structural_oc_html = structural_select_field.inputHTML(
            id_value='add_structural_oc',
            title='Structural object classes to be added',
        )
        add_auxiliary_oc_html = auxiliary_select_field.inputHTML(
            id_value='add_auxiliary_oc',
            title='Auxiliary object classes to be added',
        )
        add_abstract_oc_html = abstract_select_field.inputHTML(
            id_value='add_abstract_oc',
            title='Abstract object classes to be added',
        )
        add_template_field_html = """
          <p>
            <label for="input_formtype">Form type:</label> %s
            <input type="submit" value="Next &gt;&gt;">
          </p>
          <table>
            <tr>
              <th><label for="add_structural_oc">Structural</label></th>
              <th><label for="add_auxiliary_oc">Auxiliary</label></th>
              <th><label for="add_abstract_oc">Abstract</label></th>
              %s
            </tr>
            <tr>
              <td><label for="add_structural_oc">%s</label></td>
              <td><label for="add_auxiliary_oc">%s</label></td>
              <td><label for="add_abstract_oc">%s</label></td>
              %s
            </tr>
            <tr>
              <td>%s</td>
              <td>%s</td>
              <td>&nbsp;</td>
            </tr>
          </table>
        %s
        """ % (
            app.form.field['in_ft'].inputHTML(default=input_currentformtype),
            misc_select_field_th,
            add_structural_oc_html,
            add_auxiliary_oc_html,
            add_abstract_oc_html,
            misc_select_field_td,
            dit_structure_rule_html,
            dit_content_rule_html,
            app.form.hiddenInputHTML(
                ignoreFieldNames=(
                    'dn',
                    'add_clonedn',
                    'in_ocf',
                    'in_oft',
                    'in_ft',
                    'in_wrtattroids',
                )
            ),
        )
        Msg = {
            'add': 'Choose object class(es) for new entry.',
            'modify': 'You may change the object class(es) for the entry.',
        }[app.command]
        Msg = '<p class="WarningMessage">%s</p>' % (Msg)
        return Msg, add_template_field_html # ExpertOCFields()


    def LDIFTemplateField(app, parent_dn):
        all_structural_oc, all_abstract_oc, all_auxiliary_oc = web2ldap.app.schema.object_class_categories(sub_schema, all_oc)
        addform_entry_templates_keys = web2ldap.app.cnf.GetParam(app.ls, 'addform_entry_templates', {}).keys()
        addform_parent_attrs = web2ldap.app.cnf.GetParam(app.ls, 'addform_parent_attrs', [])
        addform_entry_templates_keys.sort()
        add_tmpl_dict = {}
        for template_name in addform_entry_templates_keys:
            ldif_dn, ldif_entry = ReadLDIFTemplate(app, template_name)
            tmpl_parent_dn = web2ldap.ldaputil.base.parent_dn(ldif_dn.decode(app.ls.charset)).decode(app.ls.charset) or parent_dn
            # first check whether mandatory attributes in parent entry are readable
            if addform_parent_attrs:
                try:
                    parent_result = app.ls.readEntry(tmpl_parent_dn, attrtype_list=addform_parent_attrs)
                except (ldap0.NO_SUCH_OBJECT, ldap0.INSUFFICIENT_ACCESS):
                    continue
                if not parent_result:
                    continue
                parent_entry = ldap0.schema.models.Entry(sub_schema, parent_result[0][0], parent_result[0][1])
                missing_parent_attrs = set([
                    attr_type
                    for attr_type in addform_parent_attrs
                    if attr_type not in parent_entry
                ])
                if missing_parent_attrs:
                    continue
            restricted_structural_oc, dit_structure_rule_html = get_possible_soc(app.ls, sub_schema, tmpl_parent_dn)
            if sub_schema.sed[DITStructureRule]:
                parent_gov_structure_rule = app.ls.getGoverningStructureRule(tmpl_parent_dn, sub_schema)
                if parent_gov_structure_rule is None:
                    restricted_structural_oc = restricted_structural_oc or all_structural_oc
                else:
                    restricted_structural_oc = restricted_structural_oc or []
            else:
                restricted_structural_oc = all_structural_oc
            restricted_structural_oc_set = ldap0.schema.models.SchemaElementOIDSet(
                sub_schema,
                ObjectClass,
                restricted_structural_oc
            )
            entry = ldap0.schema.models.Entry(sub_schema, ldif_dn, ldif_entry)
            soc = entry.get_structural_oc()
            if soc and soc in restricted_structural_oc_set:
                try:
                    add_tmpl_dict[tmpl_parent_dn].append(template_name)
                except KeyError:
                    add_tmpl_dict[tmpl_parent_dn] = [template_name]
        if not add_tmpl_dict:
            return (
                '<p class="ErrorMessage">No usable LDIF templates here. Wrong %s?</p>' % (
                    app.anchor(
                        'dit', 'sub-tree',
                        [('dn', app.dn)],
                        title=u'browse directory tree',
                    )
                ),
                '',
            )
        add_template_html_list = ['<dl>']
        for pdn in sorted(add_tmpl_dict.keys()):
            add_template_html_list.append('<dt>%s<dt>' % (
                SupentryDisplayString(app, pdn, sub_schema, supentry_display_tmpl=r'%s'),
            ))
            add_template_html_list.append('<dd><ul>')
            for tmpl_name in add_tmpl_dict[pdn]:
                add_template_html_list.append(
                    '<li>%s</li>' % (
                        app.anchor(
                            'add', app.form.utf2display(tmpl_name),
                            [
                                ('dn', pdn),
                                ('add_template', tmpl_name),
                                ('in_ft', u'Template'),
                            ],
                            title=u'Add entry beneath %s\nbased on template "%s"' % (pdn, tmpl_name),
                        )
                    )
                )
            add_template_html_list.append('</ul></dd>')
        add_template_html_list.append('</dl>')
        add_template_field_html = '\n'.join(add_template_html_list)
        Msg = '<p class="WarningMessage">Choose a LDIF template and base DN for new entry</p>'
        return Msg, add_template_field_html # LDIFTemplateField()


    in_ocf = app.form.getInputValue('in_ocf', [u'tmpl'])[0]

    relax_rules_enabled = app.ls.l._get_server_ctrls('**write**').has_key(web2ldap.ldapsession.CONTROL_RELAXRULES)

    command_hidden_fields = [('dn', app.dn)]

    existing_structural_oc, existing_abstract_oc, existing_auxiliary_oc = web2ldap.app.schema.object_class_categories(sub_schema, existing_object_classes)
    all_oc = [
        (sub_schema.get_obj(ObjectClass, oid).names or (oid,))[0]
        for oid in sub_schema.listall(ObjectClass)
    ]

    if app.command == 'add':
        parent_dn = app.dn
    elif app.command == 'modify':
        parent_dn = web2ldap.ldaputil.base.parent_dn(app.dn)

    # Build an select field based on config param 'addform_entry_templates'
    if app.command == 'add' and in_ocf == u'tmpl':
        Msg, add_template_field_html = LDIFTemplateField(app, parent_dn)
    else:
        Msg, add_template_field_html = ExpertOCFields(app, sub_schema, parent_dn)

    if app.command == 'add':
        context_menu_list = [
            app.anchor('add', 'Templates', [('dn', app.dn), ('in_ocf', 'tmpl')]),
            app.anchor('add', 'Expert', [('dn', app.dn), ('in_ocf', 'exp')]),
        ]
    else:
        context_menu_list = web2ldap.app.gui.ContextMenuSingleEntry(app)

    web2ldap.app.gui.TopSection(
        app,
        H1_MSG[app.command],
        web2ldap.app.gui.MainMenu(app),
        context_menu_list=context_menu_list,
        main_div_id='Input'
    )

    # Write HTML output of object class input form
    app.outf.write(
        '<h1>%s</h1>\n%s\n</form>' % (
            H1_MSG[app.command],
            '\n'.join((
                app.form.beginFormHTML(app.command, app.sid, 'POST', None),
                ''.join([
                    app.form.hiddenFieldHTML(param_name, param_value, u'')
                    for param_name, param_value in command_hidden_fields
                ]),
                Msg,
                add_template_field_html,
            ))
        )
    )
    web2ldap.app.gui.Footer(app)
    return # ObjectClassForm()


def ReadLDIFTemplate(app, template_name):
    addform_entry_templates = web2ldap.app.cnf.GetParam(app.ls, 'addform_entry_templates', {})
    template_name_html = escape_html(template_name)
    if not addform_entry_templates.has_key(template_name):
        raise web2ldap.app.core.ErrorExit(u'LDIF template key &quot;%s&quot; not known.' % (template_name_html))
    ldif_file_name = addform_entry_templates[template_name]
    try:
        ldif_file = open(ldif_file_name, 'rb')
    except IOError:
        raise web2ldap.app.core.ErrorExit(u'I/O error opening LDIF template for &quot;%s&quot;.' % (template_name_html))
    try:
        dn, entry = list(ldap0.ldif.LDIFParser(
            ldif_file,
            ignored_attr_types=[],
            process_url_schemes=web2ldapcnf.ldif_url_schemes
        ).parse(max_entries=1))[0]
    except (IOError, ValueError):
        raise web2ldap.app.core.ErrorExit(u'Value error reading/parsing LDIF template for &quot;%s&quot;.' % (template_name_html))
    except Exception:
        raise web2ldap.app.core.ErrorExit(u'Other error reading/parsing LDIF template for &quot;%s&quot;.' % (template_name_html))
    return dn, entry # ReadLDIFTemplate()


def AttributeTypeDict(ls, param_name, param_default):
    """
    Build a list of attributes assumed in configuration to be constant while editing entry
    """
    attrs = ldap0.cidict.cidict()
    for attr_type in web2ldap.app.cnf.GetParam(ls, param_name, param_default):
        attrs[attr_type] = attr_type
    return attrs # AttributeTypeDict()


def ConfiguredConstantAttributes(ls):
    """
    Build a list of attributes assumed in configuration to be constant while editing entry
    """
    return AttributeTypeDict(
        ls,
        'modify_constant_attrs',
        ['createTimestamp', 'modifyTimestamp', 'creatorsName', 'modifiersName'],
    )


def AssertionFilter(ls, entry):
    assertion_filter_list = []
    for attr_type in ConfiguredConstantAttributes(ls).values():
        try:
            attr_values = entry[attr_type]
        except KeyError:
            continue
        else:
            assertion_filter_list.extend([
                u'(%s)' % (
                    u'='.join((
                        attr_type,
                        ldap0.filter.escape_filter_chars(attr_value, escape_mode=1),
                    ))
                )
                for attr_value in attr_values
                if attr_value is not None
            ])
    if assertion_filter_list:
        assertion_filter = u'(&%s)' % ''.join(assertion_filter_list)
    else:
        assertion_filter = u'(objectClass=*)'
    return assertion_filter # AssertionFilter()


def nomatching_attrs(sub_schema, entry, allowed_attrs_dict, required_attrs_dict):
    """
    Determine attributes which does not appear in the schema but
    do exist in the entry
    """
    nomatching_attrs_dict = ldap0.cidict.cidict()
    for at_name in entry.entry.keys():
        try:
            at_oid = sub_schema.name2oid[AttributeType][at_name]
        except KeyError:
            nomatching_attrs_dict[at_name] = None
        else:
            if not (
                    allowed_attrs_dict.has_key(at_oid) or
                    required_attrs_dict.has_key(at_oid) or
                    at_name.lower() == 'objectclass'
                ):
                nomatching_attrs_dict[at_oid] = sub_schema.get_obj(AttributeType, at_oid)
    return nomatching_attrs_dict # nomatching_attrs()


def ReadOldEntry(ls, dn, sub_schema, assertion_filter, read_attrs=None):
    """
    Retrieve all editable attribute types an entry
    """

    WRITEABLE_ATTRS_NONE = None
    WRITEABLE_ATTRS_SLAPO_ALLOWED = 1
    WRITEABLE_ATTRS_GET_EFFECTIVE_RIGHTS = 2

    server_ctrls = []

    # Build a list of attributes to be requested
    if not read_attrs:
        read_attrs = ldap0.cidict.cidict({'*': '*'})
        read_attrs.update(ConfiguredConstantAttributes(ls))
        read_attrs.update(AttributeTypeDict(ls, 'requested_attrs', []))

    # Try to request information about which attributes are writeable by the bound identity

    # Try to query attribute allowedAttributesEffective
    if '1.2.840.113556.1.4.914' in sub_schema.sed[AttributeType]:
        # Query with attribute 'allowedAttributesEffective' e.g. on MS AD or OpenLDAP with slapo-allowed
        read_attrs['allowedAttributesEffective'] = 'allowedAttributesEffective'
        write_attrs_method = WRITEABLE_ATTRS_SLAPO_ALLOWED

    else:
        write_attrs_method = WRITEABLE_ATTRS_NONE

    assert write_attrs_method in {WRITEABLE_ATTRS_NONE, WRITEABLE_ATTRS_SLAPO_ALLOWED, WRITEABLE_ATTRS_GET_EFFECTIVE_RIGHTS}, \
        ValueError('Invalid value for write_attrs_method')

    # Explicitly request attribute 'ref' if in manage DSA IT mode
    if ls.l._get_server_ctrls('**all**').has_key(web2ldap.ldapsession.CONTROL_MANAGEDSAIT):
        read_attrs['ref'] = 'ref'

    # Read the editable attribute values of entry
    try:
        ldap_entry = ls.readEntry(
            dn,
            read_attrs.values(),
            search_filter=(assertion_filter or u'(objectClass=*)').encode(ls.charset),
            no_cache=1,
            server_ctrls=server_ctrls or None,
        )[0][1]
    except IndexError:
        raise ldap0.NO_SUCH_OBJECT

    entry = ldap0.schema.models.Entry(sub_schema, dn.encode(ls.charset), ldap_entry)

    if write_attrs_method == WRITEABLE_ATTRS_NONE:
        # No method to determine writeable attributes was used
        writeable_attr_oids = None

    elif write_attrs_method == WRITEABLE_ATTRS_SLAPO_ALLOWED:
        # Determine writeable attributes from attribute 'allowedAttributesEffective'
        try:
            writeable_attr_oids = ldap0.schema.models.SchemaElementOIDSet(
                sub_schema, AttributeType, entry['allowedAttributesEffective']
            )
        except KeyError:
            writeable_attr_oids = set([])
        else:
            del entry['allowedAttributesEffective']

    elif write_attrs_method == WRITEABLE_ATTRS_GET_EFFECTIVE_RIGHTS:
        # Try to determine writeable attributes from attribute 'aclRights'
        acl_rights_attribute_level = [
            (a, v)
            for a, v in entry.data.items()
            if a[0] == '1.3.6.1.4.1.42.2.27.9.1.39' and a[1] == 'attributelevel'
        ]
        if acl_rights_attribute_level:
            writeable_attr_oids = set([])
            for a, v in acl_rights_attribute_level:
                try:
                    dummy1, dummy2, attr_type = a
                except ValueError:
                    pass
                else:
                    if v[0].lower().find(',write:1,') >= 0:
                        writeable_attr_oids.add(
                            sub_schema.getoid(AttributeType, a[2]).decode('ascii')
                        )
                del entry[';'.join((dummy1, dummy2, attr_type))]

    return entry, writeable_attr_oids # ReadOldEntry()


def w2l_addform(
        app,
        add_rdn, add_basedn, entry, Msg='', invalid_attrs=None,
    ):

    if Msg:
        Msg = '<p class="ErrorMessage">%s</p>' % (Msg)

    sub_schema = app.ls.retrieveSubSchema(
        app.dn,
        web2ldap.app.cnf.GetParam(app.ls, '_schema', None),
        web2ldap.app.cnf.GetParam(app.ls, 'supplement_schema', None),
        web2ldap.app.cnf.GetParam(app.ls, 'schema_strictcheck', True),
    )

    input_formtype = app.form.getInputValue(
        'in_ft',
        app.form.getInputValue('in_oft', ['OC'])
    )[0]

    if 'in_oc' in app.form.inputFieldNames:
        # Read objectclass(es) from input form
        entry['objectClass'] = [oc.encode('ascii') for oc in app.form.field['in_oc'].value]

    if input_formtype == 'OC' or not entry:
        # Output the web page with object class input form
        ObjectClassForm(app, sub_schema, entry.get('objectClass', []), None)
        return

    input_form_entry = InputFormEntry(app, app.dn, sub_schema, entry, None, invalid_attrs=invalid_attrs)
    required_attrs_dict, allowed_attrs_dict = input_form_entry.attribute_types()
    nomatching_attrs_dict = nomatching_attrs(sub_schema, input_form_entry, allowed_attrs_dict, required_attrs_dict)

    rdn_options = input_form_entry.entry.get_rdn_templates()

    supentry_display_string = SupentryDisplayString(app, add_basedn, sub_schema)

    if rdn_options and len(rdn_options) > 0:
        # <select> field
        rdn_input_field = web2ldap.web.forms.Select('add_rdn', 'RDN variants', 1, options=rdn_options)
    else:
        # Just a normal <input> text field
        rdn_input_field = app.form.field['add_rdn']
    if add_rdn:
        rdn_input_field.setDefault(add_rdn)
    else:
        rdn_candidate_attr_nameoroids = [
            (required_attrs_dict[at_oid].names or (at_oid,))[0]
            for at_oid in required_attrs_dict.keys()
            if at_oid != '2.5.4.0' and not web2ldap.app.schema.no_humanreadable_attr(sub_schema, at_oid)
        ]
        if len(rdn_candidate_attr_nameoroids) == 1:
            rdn_input_field.setDefault(rdn_candidate_attr_nameoroids[0]+'=')

    relax_rules_enabled = app.ls.l._get_server_ctrls('**write**').has_key(web2ldap.ldapsession.CONTROL_RELAXRULES)
    if relax_rules_enabled:
        Msg = ''.join((
            Msg,
            '<p class="WarningMessage">Relax Rules Control enabled! Be sure you know what you are doing!</p>',
        ))

    # Check whether to fall back to table input mode
    if input_formtype == u'Template':
        template_oc, read_template_dict = input_form_entry.get_html_templates('input_template')
        if not template_oc:
            Msg = ''.join((
                Msg,
                '<p class="WarningMessage">No templates defined for chosen object classes.</p>'
            ))
            input_formtype = u'Table'
        elif relax_rules_enabled:
            Msg = ''.join((
                Msg,
                '<p class="WarningMessage">Forced to table input because Relax Rules Control is enabled.</p>'
            ))
            input_formtype = u'Table'

    web2ldap.app.gui.TopSection(
        app,
        H1_MSG[app.command],
        web2ldap.app.gui.MainMenu(app),
        context_menu_list=[]
    )

    app.outf.write(
        INPUT_FORM_BEGIN_TMPL.format(
            text_heading=H1_MSG[app.command],
            text_msg=Msg,
            text_supentry=supentry_display_string,
            form_begin=app.form.beginFormHTML(app.command, app.sid, 'POST', target=None, enctype='multipart/form-data'),
            field_dn=app.form.hiddenFieldHTML('dn', app.dn, u''),
            field_currentformtype=app.form.hiddenFieldHTML('in_oft', unicode(input_formtype), u''),
            text_submit=app.command[0].upper()+app.command[1:],
        )
    )

    app.outf.write(
        '%s\n<p>RDN: %s</p>\n%s' % (
            app.form.hiddenFieldHTML('add_basedn', add_basedn, u''),
            rdn_input_field.inputHTML(),
            app.form.hiddenFieldHTML('in_ocf', u'exp', u''),
        )
    )

    if input_formtype == u'Template':
        input_form_entry.template_output(
            'input_template',
            display_duplicate_attrs=False
        )
    elif input_formtype == u'Table':
        input_form_entry.table_input(
            (
                (required_attrs_dict, 'Required attributes'),
                (allowed_attrs_dict, 'Allowed attributes'),
                (nomatching_attrs_dict, 'Other attributes'),
            )
        )
    elif input_formtype == u'LDIF':
        input_form_entry.ldif_input()

    app.outf.write('</form>')
    web2ldap.app.gui.Footer(app)
    return # w2l_addform()


def w2l_modifyform(app, entry, Msg='', invalid_attrs=None):

    if Msg:
        Msg = '<p class="ErrorMessage">%s</p>' % (Msg)

    sub_schema = app.ls.retrieveSubSchema(
        app.dn,
        web2ldap.app.cnf.GetParam(app.ls, '_schema', None),
        web2ldap.app.cnf.GetParam(app.ls, 'supplement_schema', None),
        web2ldap.app.cnf.GetParam(app.ls, 'schema_strictcheck', True),
    )

    input_formtype = app.form.getInputValue(
        'in_ft',
        app.form.getInputValue('in_oft', ['Template'])
    )[0]

    if 'in_oc' in app.form.inputFieldNames:
        # Read objectclass(es) from input form
        entry['objectClass'] = [oc.encode('ascii') for oc in app.form.field['in_oc'].value]

    old_entry, read_writeable_attr_oids = ReadOldEntry(app.ls, app.dn, sub_schema, None)
    if not entry:
        entry = old_entry

    in_wrtattroids = app.form.getInputValue('in_wrtattroids', [])
    if in_wrtattroids == ['nonePseudoValue;x-web2ldap-None']:
        writeable_attr_oids = None
    elif in_wrtattroids:
        writeable_attr_oids = set([a.encode(app.ls.charset) for a in in_wrtattroids])
    else:
        writeable_attr_oids = read_writeable_attr_oids

    if input_formtype == 'OC':
        # Output the web page with object class input form
        ObjectClassForm(
            app, sub_schema,
            entry['objectClass'],
            entry.get_structural_oc(),
        )
        return

    existing_object_classes = entry['objectClass'][:]

    input_form_entry = InputFormEntry(
        app, app.dn, sub_schema,
        entry, writeable_attr_oids, existing_object_classes, invalid_attrs=invalid_attrs
    )
    required_attrs_dict, allowed_attrs_dict = input_form_entry.attribute_types()
    nomatching_attrs_dict = nomatching_attrs(sub_schema, input_form_entry, allowed_attrs_dict, required_attrs_dict)

    supentry_display_string = SupentryDisplayString(app, web2ldap.ldaputil.base.parent_dn(app.dn), sub_schema)

    if writeable_attr_oids is None:
        in_wrtattroids_values = app.form.hiddenFieldHTML('in_wrtattroids', u'nonePseudoValue;x-web2ldap-None', u'')
    else:
        in_wrtattroids_values = ''.join([
            app.form.hiddenFieldHTML('in_wrtattroids', at_name.decode('ascii'), u'')
            for at_name in writeable_attr_oids or []
        ])

    relax_rules_enabled = app.ls.l._get_server_ctrls('**write**').has_key(web2ldap.ldapsession.CONTROL_RELAXRULES)
    if relax_rules_enabled:
        Msg = ''.join((
            Msg,
            '<p class="WarningMessage">Relax Rules Control enabled! Be sure you know what you are doing!</p>',
        ))

    # Check whether to fall back to table input mode
    if input_formtype == u'Template':
        template_oc, read_template_dict = input_form_entry.get_html_templates('input_template')
        if not template_oc:
            Msg = ''.join((
                Msg,
                '<p class="WarningMessage">No templates defined for chosen object classes.</p>',
            ))
            input_formtype = u'Table'
        elif relax_rules_enabled:
            Msg = ''.join((
                Msg,
                '<p class="WarningMessage">Forced to table input because Relax Rules Control is enabled.</p>',
            ))
            input_formtype = u'Table'

    web2ldap.app.gui.TopSection(
        app,
        H1_MSG[app.command],
        web2ldap.app.gui.MainMenu(app),
        context_menu_list=web2ldap.app.gui.ContextMenuSingleEntry(app)
    )

    app.outf.write(
        INPUT_FORM_BEGIN_TMPL.format(
            text_heading=H1_MSG[app.command],
            text_msg=Msg,
            text_supentry=supentry_display_string,
            form_begin=app.form.beginFormHTML(
                app.command, app.sid, 'POST',
                target=None,
                enctype='multipart/form-data',
            ),
            field_dn=app.form.hiddenFieldHTML('dn', app.dn, u''),
            field_currentformtype=app.form.hiddenFieldHTML('in_oft', input_formtype.decode('ascii'), u''),
            text_submit=app.command[0].upper()+app.command[1:],
        )
    )

    app.outf.write('\n'.join((
        app.form.hiddenFieldHTML('in_assertion', AssertionFilter(app.ls, entry), u''),
        '\n'.join([
            app.form.hiddenFieldHTML('in_oldattrtypes', at_name.decode('ascii'), u'')
            for at_name in app.form.getInputValue('in_oldattrtypes', entry.keys())
        ]),
        in_wrtattroids_values,
    )))

    if input_formtype == u'Template':
        input_form_entry.template_output(
            'input_template',
            display_duplicate_attrs=False
        )

    elif input_formtype == u'Table':
        input_form_entry.table_input(
            (
                (required_attrs_dict, 'Required attributes'),
                (allowed_attrs_dict, 'Allowed attributes'),
                (nomatching_attrs_dict, 'Other attributes'),
            )
        )

    elif input_formtype == u'LDIF':
        input_form_entry.ldif_input()

    app.outf.write('</form>')
    web2ldap.app.gui.Footer(app)
    return # w2l_modifyform()

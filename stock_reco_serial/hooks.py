# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from . import __version__ as app_version

app_name = "stock_reco_serial"
app_title = "Stock Reco Serial"
app_publisher = "Craft"
app_description = "Customization for Stock Reco"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "hafeesk@gmail.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/stock_reco_serial/css/stock_reco_serial.css"
# app_include_js = "/assets/stock_reco_serial/js/stock_reco_serial.js"

# include js, css files in header of web template
# web_include_css = "/assets/stock_reco_serial/css/stock_reco_serial.css"
# web_include_js = "/assets/stock_reco_serial/js/stock_reco_serial.js"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"Stock Reconciliation" : "public/js/stock_reco.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Website user home page (by function)
# get_website_user_home_page = "stock_reco_serial.utils.get_home_page"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "stock_reco_serial.install.before_install"
# after_install = "stock_reco_serial.install.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "stock_reco_serial.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [
            [
                "name",
                "in",
                [
                    "Stock Reconciliation Item-avg_valuation_rate",
                    "Stock Reconciliation Item-serial_and_batch_section_",
                    "Stock Reconciliation Item-serial_no",
                    "Stock Reconciliation Item-column_craft",
                    "Stock Reconciliation Item-batch_no",
                    "Stock Reconciliation Item-current_serial_no"
                ]
            ]
        ]
    }
]

doc_events = {
    "Stock Reconciliation": {
            "before_save": "stock_reco_serial.stock_reco_serial.stock_reco.override_methods",
            "before_submit": "stock_reco_serial.stock_reco_serial.stock_reco.override_methods",
            "before_insert": "stock_reco_serial.stock_reco_serial.stock_reco.override_methods",
    },
}
# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"stock_reco_serial.tasks.all"
# 	],
# 	"daily": [
# 		"stock_reco_serial.tasks.daily"
# 	],
# 	"hourly": [
# 		"stock_reco_serial.tasks.hourly"
# 	],
# 	"weekly": [
# 		"stock_reco_serial.tasks.weekly"
# 	]
# 	"monthly": [
# 		"stock_reco_serial.tasks.monthly"
# 	]
# }

# Testing
# -------

# before_tests = "stock_reco_serial.install.before_tests"

# Overriding Whitelisted Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "stock_reco_serial.event.get_events"
# }



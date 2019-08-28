import frappe
from erpnext.stock.utils import get_stock_balance, get_incoming_rate
from frappe import msgprint, _
from frappe.utils import cstr, flt, cint
from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos
from erpnext.stock.stock_ledger import update_entries_after
import json


class EmptyStockReconciliationItemsError(frappe.ValidationError):
    pass


@frappe.whitelist()
def get_serial_item_data(item_code=None, warehouse=None, posting_date=None, posting_time=None, batch_no=None, with_valuation_rate=True):
    if item_code:
        current_stock = frappe.db.sql(
            """select sum(actual_qty) from `tabBin` where item_code = '{}' """.format(item_code))

        sle = frappe.db.sql(
            """select incoming_rate,actual_qty from `tabStock Ledger Entry` where item_code='{}' and voucher_type='Purchase Invoice' order by posting_date desc""".format(item_code))
        count = 0.00
        lst_item = []
        valuation_rate = 0.00
        if current_stock:

            for item in sle:
                count = count + item[1]

                lst_item.append([item[0], item[1], item[0]*item[1]])

                if count >= current_stock[0][0]:
                    break

            qty_sum = 0.00
            price_sum = 0.00
            for data in lst_item:
                qty_sum = qty_sum + data[1]
                price_sum = price_sum + data[2]

            if lst_item:
                valuation_rate = price_sum/qty_sum

        item_dict = frappe.db.get_value(
            "Item", item_code, ["has_serial_no", "has_batch_no"], as_dict=1)

        serial_nos = ""
        if item_dict.get("has_serial_no"):
            qty, rate, serial_nos = get_qty_rate_for_serial_nos(item_code,
                                                                warehouse, posting_date, posting_time, item_dict)
        else:
            qty, rate = get_stock_balance(item_code, warehouse,
                                          posting_date, posting_time, with_valuation_rate=with_valuation_rate)

        if item_dict.get("has_batch_no"):
            qty = get_batch_qty(batch_no, warehouse) or 0

        return {
            'qty': qty,
            'rate': rate,
            'serial_nos': serial_nos,
            'valuation_rate': valuation_rate
        }


def get_available_serial_nos(item_code, warehouse):
    return frappe.get_all("Serial No", filters={'item_code': item_code,
                                                'warehouse': warehouse, 'delivery_document_no': ''}) or []


def custom_validate(self):
    if not self.expense_account:
        self.expense_account = frappe.get_cached_value(
            'Company',  self.company,  "stock_adjustment_account")
    if not self.cost_center:
        self.cost_center = frappe.get_cached_value(
            'Company',  self.company,  "cost_center")
    self.validate_posting_time()
    custom_remove_items_with_no_change(self)
    custom_validate_data(self)
    self.validate_expense_account()
    self.set_total_qty_and_amount()


def custom_remove_items_with_no_change(self):
    """Remove items if qty or rate is not changed"""
    self.difference_amount = 0.0

    def _changed(item):
        item_dict = get_stock_balance_for(item.item_code, item.warehouse,
                                          self.posting_date, self.posting_time, batch_no_craft=item.batch_no_craft)

        if (((item.qty is None or item.qty == item_dict.get("qty")) and
                (item.valuation_rate is None or item.valuation_rate == item_dict.get("rate")) and not item.serial_no_craft)):
            return False
        else:
            # set default as current rates
            if item.qty is None:
                item.qty = item_dict.get("qty")

            if item.valuation_rate is None:
                item.valuation_rate = item_dict.get("rate")

            if item_dict.get("serial_nos"):
                item.current_serial_no_craft = item_dict.get("serial_nos")

            item.current_qty = item_dict.get("qty")
            item.current_valuation_rate = item_dict.get("rate")
            self.difference_amount += (flt(item.qty, item.precision("qty")) *
                                       flt(item.valuation_rate or item_dict.get(
                                           "rate"), item.precision("valuation_rate"))
                                       - flt(item_dict.get("qty"), item.precision("qty")) * flt(item_dict.get("rate"), item.precision("valuation_rate")))
            return True

    items = list(filter(lambda d: _changed(d), self.items))

    if not items:
        frappe.throw(_("None of the items have any change in quantity or value."),
                     EmptyStockReconciliationItemsError)

    elif len(items) != len(self.items):
        self.items = items
        for i, item in enumerate(self.items):
            item.idx = i + 1
        frappe.msgprint(
            _("Removed items with no change in quantity or value."))


def get_stock_balance_for(item_code, warehouse,
                          posting_date, posting_time, batch_no_craft=None, with_valuation_rate=True):
    frappe.has_permission("Stock Reconciliation", "write", throw=True)

    item_dict = frappe.db.get_value("Item", item_code,
                                    ["has_serial_no", "has_batch_no"], as_dict=1)

    serial_nos = ""
    if item_dict.get("has_serial_no"):
        qty, rate, serial_nos = get_qty_rate_for_serial_nos(item_code,
                                                            warehouse, posting_date, posting_time, item_dict)
    else:
        qty, rate = get_stock_balance(item_code, warehouse,
                                      posting_date, posting_time, with_valuation_rate=with_valuation_rate)

    if item_dict.get("has_batch_no"):
        qty = get_batch_qty(batch_no_craft, warehouse) or 0

    return {
        'qty': qty,
        'rate': rate,
        'serial_nos': serial_nos
    }


def get_qty_rate_for_serial_nos(item_code, warehouse, posting_date, posting_time, item_dict):
    args = {
        "item_code": item_code,
        "warehouse": warehouse,
        "posting_date": posting_date,
        "posting_time": posting_time,
    }

    serial_nos_list = [serial_no.get("name")
                       for serial_no in get_available_serial_nos(item_code, warehouse)]

    qty = len(serial_nos_list)
    serial_nos = '\n'.join(serial_nos_list)
    args.update({
        'qty': qty,
        "serial_nos": serial_nos
    })

    rate = get_incoming_rate(args, raise_error_if_no_rate=False) or 0

    return qty, rate, serial_nos


def custom_validate_data(self):
    def _get_msg(row_num, msg):
        return _("Row # {0}: ").format(row_num+1) + msg

    self.validation_messages = []
    item_warehouse_combinations = []

    default_currency = frappe.db.get_default("currency")

    for row_num, row in enumerate(self.items):
        # find duplicates
        key = [row.item_code, row.warehouse]
        for field in ['serial_no_craft', 'batch_no_craft']:
            if row.get(field):
                key.append(row.get(field))

        if key in item_warehouse_combinations:
            self.validation_messages.append(
                _get_msg(row_num, _("Duplicate entry")))
        else:
            item_warehouse_combinations.append(key)

        custom_validate_item(self, row.item_code, row)

        # validate warehouse
        if not frappe.db.get_value("Warehouse", row.warehouse):
            self.validation_messages.append(
                _get_msg(row_num, _("Warehouse not found in the system")))

        # if both not specified
        if row.qty in ["", None] and row.valuation_rate in ["", None]:
            self.validation_messages.append(_get_msg(row_num,
                                                     _("Please specify either Quantity or Valuation Rate or both")))

        # do not allow negative quantity
        if flt(row.qty) < 0:
            self.validation_messages.append(_get_msg(row_num,
                                                     _("Negative Quantity is not allowed")))

        # do not allow negative valuation
        if flt(row.valuation_rate) < 0:
            self.validation_messages.append(_get_msg(row_num,
                                                     _("Negative Valuation Rate is not allowed")))

        if row.qty and row.valuation_rate in ["", None]:
            row.valuation_rate = get_stock_balance(row.item_code, row.warehouse,
                                                   self.posting_date, self.posting_time, with_valuation_rate=True)[1]
            if not row.valuation_rate:
                # try if there is a buying price list in default currency
                buying_rate = frappe.db.get_value("Item Price", {"item_code": row.item_code,
                                                                 "buying": 1, "currency": default_currency}, "price_list_rate")
                if buying_rate:
                    row.valuation_rate = buying_rate

                else:
                    # get valuation rate from Item
                    row.valuation_rate = frappe.get_value(
                        'Item', row.item_code, 'valuation_rate')

    # throw all validation messages
    if self.validation_messages:
        for msg in self.validation_messages:
            msgprint(msg)

        raise frappe.ValidationError(self.validation_messages)


def custom_validate_item(self, item_code, row):
    from erpnext.stock.doctype.item.item import validate_end_of_life, \
        validate_is_stock_item, validate_cancelled_item

    # using try except to catch all validation msgs and display together

    try:
        item = frappe.get_doc("Item", item_code)

        # end of life and stock item
        validate_end_of_life(item_code, item.end_of_life,
                             item.disabled, verbose=0)
        validate_is_stock_item(item_code, item.is_stock_item, verbose=0)

        # item should not be serialized
        if item.has_serial_no and not row.serial_no_craft and not item.serial_no_series:
            raise frappe.ValidationError(
                _("Serial no(s) required for serialized item {0}").format(item_code))

        # item managed batch-wise not allowed
        if item.has_batch_no and not row.batch_no_craft and not item.create_new_batch:
            raise frappe.ValidationError(
                _("Batch no is required for batched item {0}").format(item_code))

        # docstatus should be < 2
        validate_cancelled_item(item_code, item.docstatus, verbose=0)

    except Exception as e:
        self.validation_messages.append(
            _("Row # ") + ("%d: " % (row.idx)) + cstr(e))


def custom_submit(self):
    self.update_stock_ledger()
    self.make_gl_entries()

    # from erpnext.stock.doctype.serial_no.serial_no import update_serial_nos_after_submit
    # update_serial_nos_after_submit(self, "items")

    stock_ledger_entries = frappe.db.sql("""select voucher_detail_no, serial_no, actual_qty, warehouse
                        from `tabStock Ledger Entry` where voucher_type=%s and voucher_no=%s""",
                                         (self.doctype, self.name), as_dict=True)

    if not stock_ledger_entries:
        return

    for d in self.get("items"):
        update_rejected_serial_nos = True if (self.doctype in ("Purchase Receipt", "Purchase Invoice")
                                              and d.rejected_qty) else False
        accepted_serial_nos_updated = False
        if self.doctype == "Stock Entry":
            warehouse = d.t_warehouse
            qty = d.transfer_qty
        else:
            warehouse = d.warehouse
            qty = (d.qty if self.doctype == "Stock Reconciliation"
                   else d.stock_qty)

        for sle in stock_ledger_entries:
            if sle.voucher_detail_no == d.name:
                if not accepted_serial_nos_updated and qty and abs(sle.actual_qty) == qty \
                        and sle.warehouse == warehouse and sle.serial_no != d.serial_no_craft:
                    d.serial_no_craft = sle.serial_no
                    frappe.db.set_value(d.doctype, d.name,
                                        "serial_no_craft", sle.serial_no)
                    accepted_serial_nos_updated = True
                    if not update_rejected_serial_nos:
                        break
                elif update_rejected_serial_nos and abs(sle.actual_qty) == d.rejected_qty \
                        and sle.warehouse == d.rejected_warehouse and sle.serial_no != d.rejected_serial_no:
                    d.rejected_serial_no = sle.serial_no
                    frappe.db.set_value(d.doctype, d.name,
                                        "rejected_serial_no", sle.serial_no)
                    update_rejected_serial_nos = False
                    if accepted_serial_nos_updated:
                        break


def update_stock_ledger(self):
    """	find difference between current and expected entries
            and create stock ledger entries based on the difference"""
    from erpnext.stock.stock_ledger import get_previous_sle

    sl_entries = []
    for row in self.items:
        item = frappe.get_doc("Item", row.item_code)
        if item.has_serial_no or item.has_batch_no:
            self.get_sle_for_serialized_items(row, sl_entries)
        else:
            previous_sle = get_previous_sle({
                "item_code": row.item_code,
                "warehouse": row.warehouse,
                "posting_date": self.posting_date,
                "posting_time": self.posting_time
            })

            if previous_sle:
                if row.qty in ("", None):
                    row.qty = previous_sle.get("qty_after_transaction", 0)

                if row.valuation_rate in ("", None):
                    row.valuation_rate = previous_sle.get("valuation_rate", 0)

            if row.qty and not row.valuation_rate:
                frappe.throw(_("Valuation Rate required for Item {0} at row {1}").format(
                    row.item_code, row.idx))

            if ((previous_sle and row.qty == previous_sle.get("qty_after_transaction")
                    and (row.valuation_rate == previous_sle.get("valuation_rate") or row.qty == 0))
                    or (not previous_sle and not row.qty)):
                continue

            sl_entries.append(self.get_sle_for_items(row))

    if sl_entries:
        self.make_sl_entries(sl_entries)


def get_sle_for_serialized_items(self, row, sl_entries):
    from erpnext.stock.stock_ledger import get_previous_sle

    serial_nos = get_serial_nos(row.serial_no_craft)

    # To issue existing serial nos
    if row.current_qty and (row.current_serial_no_craft or row.batch_no_craft):
        args = self.get_sle_for_items(row)
        args.update({
            'actual_qty': -1 * row.current_qty,
            'serial_no': row.current_serial_no_craft,
            'batch_no': row.batch_no_craft,
            'valuation_rate': row.current_valuation_rate
        })

        if row.current_serial_no_craft:
            args.update({
                'qty_after_transaction': 0,
            })

        sl_entries.append(args)

    for serial_no in serial_nos:
        args = self.get_sle_for_items(row, [serial_no])

        previous_sle = get_previous_sle({
            "item_code": row.item_code,
            "posting_date": self.posting_date,
            "posting_time": self.posting_time,
            "serial_no": serial_no
        })

        if previous_sle and row.warehouse != previous_sle.get("warehouse"):
            # If serial no exists in different warehouse

            new_args = args.copy()
            new_args.update({
                'actual_qty': -1,
                'qty_after_transaction': cint(previous_sle.get('qty_after_transaction')) - 1,
                'warehouse': previous_sle.get("warehouse", '') or row.warehouse,
                'valuation_rate': previous_sle.get("valuation_rate")
            })

            sl_entries.append(new_args)

    if row.qty:
        args = self.get_sle_for_items(row)

        args.update({
            'actual_qty': row.qty,
            'incoming_rate': row.valuation_rate,
            'valuation_rate': row.valuation_rate
        })

        sl_entries.append(args)

    if serial_nos == get_serial_nos(row.current_serial_no_craft):
        # update valuation rate
        self.update_valuation_rate_for_serial_nos(row, serial_nos)


def update_valuation_rate_for_serial_nos(self, row, serial_nos):
    valuation_rate = row.valuation_rate if self.docstatus == 1 else row.current_valuation_rate
    for d in serial_nos:
        frappe.db.set_value("Serial No", d, 'purchase_rate', valuation_rate)


def get_sle_for_items(self, row, serial_nos=None):
    """Insert Stock Ledger Entries"""

    if not serial_nos and row.serial_no_craft:
        serial_nos = get_serial_nos(row.serial_no_craft)

    data = frappe._dict({
        "doctype": "Stock Ledger Entry",
        "item_code": row.item_code,
        "warehouse": row.warehouse,
        "posting_date": self.posting_date,
        "posting_time": self.posting_time,
        "voucher_type": self.doctype,
        "voucher_no": self.name,
        "voucher_detail_no": row.name,
        "company": self.company,
        "stock_uom": frappe.db.get_value("Item", row.item_code, "stock_uom"),
        "is_cancelled": "No" if self.docstatus != 2 else "Yes",
        "serial_no": '\n'.join(serial_nos) if serial_nos else '',
        "batch_no": row.batch_no_craft,
        "valuation_rate": flt(row.valuation_rate, row.precision("valuation_rate"))
    })

    if not row.batch_no_craft:
        data.qty_after_transaction = flt(row.qty, row.precision("qty"))

    return data


def delete_and_repost_sle(self):
    """     Delete Stock Ledger Entries related to this voucher
            and repost future Stock Ledger Entries"""

    existing_entries = frappe.db.sql("""select distinct item_code, warehouse
                        from `tabStock Ledger Entry` where voucher_type=%s and voucher_no=%s""",
                                     (self.doctype, self.name), as_dict=1)

    # delete entries
    frappe.db.sql("""delete from `tabStock Ledger Entry`
                        where voucher_type=%s and voucher_no=%s""", (self.doctype, self.name))

    sl_entries = []
    for row in self.items:
        if row.serial_no_craft or row.batch_no_craft or row.current_serial_no_craft:
            self.get_sle_for_serialized_items(row, sl_entries)

    if sl_entries:
        sl_entries.reverse()
        self.make_sl_entries(sl_entries)

    # repost future entries for selected item_code, warehouse
    for entries in existing_entries:
        update_entries_after({
            "item_code": entries.item_code,
            "warehouse": entries.warehouse,
            "posting_date": self.posting_date,
            "posting_time": self.posting_time
        })


def process_sle(self, sle):
    if (sle.serial_no and not self.via_landed_cost_voucher) or not cint(self.allow_negative_stock):
        # validate negative stock for serialized items, fifo valuation
        # or when negative stock is not allowed for moving average
        if not self.validate_negative_stock(sle):
            self.qty_after_transaction += flt(sle.actual_qty)
            return

    if sle.serial_no:
        self.get_serialized_values(sle)
        self.qty_after_transaction += flt(sle.actual_qty)
        if sle.voucher_type == "Stock Reconciliation":
            self.qty_after_transaction = sle.qty_after_transaction

        self.stock_value = flt(self.qty_after_transaction) * \
            flt(self.valuation_rate)
    else:
        if sle.voucher_type == "Stock Reconciliation" and not sle.batch_no:
            # assert
            self.valuation_rate = sle.valuation_rate
            self.qty_after_transaction = sle.qty_after_transaction
            self.stock_queue = [
                [self.qty_after_transaction, self.valuation_rate]]
            self.stock_value = flt(
                self.qty_after_transaction) * flt(self.valuation_rate)
        else:
            if self.valuation_method == "Moving Average":
                self.get_moving_average_values(sle)
                self.qty_after_transaction += flt(sle.actual_qty)
                self.stock_value = flt(
                    self.qty_after_transaction) * flt(self.valuation_rate)
            else:
                self.get_fifo_values(sle)
                self.qty_after_transaction += flt(sle.actual_qty)
                self.stock_value = sum(
                    (flt(batch[0]) * flt(batch[1]) for batch in self.stock_queue))

    # rounding as per precision
    self.stock_value = flt(self.stock_value, self.precision)

    if self.prev_stock_value < 0 and self.stock_value >= 0 and sle.voucher_type != 'Stock Reconciliation':
        stock_value_difference = sle.actual_qty * self.valuation_rate
    else:
        stock_value_difference = self.stock_value - self.prev_stock_value

    self.prev_stock_value = self.stock_value

    # update current sle
    sle.qty_after_transaction = self.qty_after_transaction
    sle.valuation_rate = self.valuation_rate
    sle.stock_value = self.stock_value
    sle.stock_queue = json.dumps(self.stock_queue)
    sle.stock_value_difference = stock_value_difference
    sle.doctype = "Stock Ledger Entry"
    frappe.get_doc(sle).db_update()


def get_stock_ledger_entries(previous_sle, operator=None,
                             order="desc", limit=None, for_update=False, debug=False, check_serial_no=True):
    """get stock ledger entries filtered by specific posting datetime conditions"""
    conditions = " and timestamp(posting_date, posting_time) {0} timestamp(%(posting_date)s, %(posting_time)s)".format(
        operator)
    if previous_sle.get("warehouse"):
        conditions += " and warehouse = %(warehouse)s"
    elif previous_sle.get("warehouse_condition"):
        conditions += " and " + previous_sle.get("warehouse_condition")

    if check_serial_no and previous_sle.get("serial_no"):
        conditions += " and serial_no like '{}'".format(
            frappe.db.escape('%{0}%'.format(previous_sle.get("serial_no"))))

    if not previous_sle.get("posting_date"):
        previous_sle["posting_date"] = "1900-01-01"
    if not previous_sle.get("posting_time"):
        previous_sle["posting_time"] = "00:00"

    if operator in (">", "<=") and previous_sle.get("name"):
        conditions += " and name!=%(name)s"

    return frappe.db.sql("""select *, timestamp(posting_date, posting_time) as "timestamp" from `tabStock Ledger Entry`
                where item_code = %%(item_code)s
                and ifnull(is_cancelled, 'No')='No'
                %(conditions)s
                order by timestamp(posting_date, posting_time) %(order)s, creation %(order)s
                %(limit)s %(for_update)s""" % {
        "conditions": conditions,
        "limit": limit or "",
        "for_update": for_update and "for update" or "",
        "order": order
    }, previous_sle, as_dict=1, debug=debug)


def get_sle_after_datetime(self):
    """get Stock Ledger Entries after a particular datetime, for reposting"""
    return get_stock_ledger_entries(self.previous_sle or frappe._dict({
        "item_code": self.args.get("item_code"), "warehouse": self.args.get("warehouse")}),
        ">", "asc", for_update=True, check_serial_no=False)


def override_methods(args, status):
    from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import StockReconciliation
    from erpnext.stock.stock_ledger import update_entries_after
    import erpnext.stock.stock_ledger
    StockReconciliation.validate = custom_validate
    StockReconciliation.on_submit = custom_submit
    StockReconciliation.get_sle_for_items = get_sle_for_items
    StockReconciliation.update_stock_ledger = update_stock_ledger
    StockReconciliation.get_sle_for_serialized_items = get_sle_for_serialized_items
    StockReconciliation.update_valuation_rate_for_serial_nos = update_valuation_rate_for_serial_nos
    StockReconciliation.delete_and_repost_sle = delete_and_repost_sle
    update_entries_after.process_sle = process_sle
    erpnext.stock.stock_ledger.get_stock_ledger_entries = get_stock_ledger_entries
    update_entries_after.get_sle_after_datetime = get_sle_after_datetime

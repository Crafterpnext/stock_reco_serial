import frappe
from erpnext.stock.utils import get_stock_balance, get_incoming_rate
from erpnext.stock.utils import get_stock_balance, get_incoming_rate, get_available_serial_nos
from frappe import msgprint, _
from frappe.utils import cstr, flt, cint

class EmptyStockReconciliationItemsError(frappe.ValidationError): pass


@frappe.whitelist()
def get_serial_item_data(item_code=None):
		current_stock = frappe.db.sql("""select sum(actual_qty) from `tabBin` where item_code = '{}' """.format(item_code))

		sle = frappe.db.sql("""select incoming_rate,actual_qty from `tabStock Ledger Entry` where item_code='{}' and voucher_type='Purchase Invoice' order by posting_date desc""".format(item_code))
		count = 0.00
		lst_item = []
		valuation_rate = 0.00
		if current_stock:

			for item in sle:
				count = count + item[1]
				
				lst_item.append([item[0],item[1],item[0]*item[1]])
				
				if count >= current_stock[0][0]:
					break

			qty_sum = 0.00
			price_sum = 0.00
			for data in lst_item:
				qty_sum = qty_sum + data[1]
				price_sum = price_sum + data[2]

			if lst_item:
				valuation_rate = price_sum/qty_sum


		return {'valuation_rate':valuation_rate}

def custom_validate(self):
		if not self.expense_account:
			self.expense_account = frappe.get_cached_value('Company',  self.company,  "stock_adjustment_account")
		if not self.cost_center:
			self.cost_center = frappe.get_cached_value('Company',  self.company,  "cost_center")
		self.validate_posting_time()
		custom_remove_items_with_no_change(self)
		self.validate_data()
		self.validate_expense_account()
		self.set_total_qty_and_amount()


def custom_remove_items_with_no_change(self):
		"""Remove items if qty or rate is not changed"""
		self.difference_amount = 0.0
		def _changed(item):
			item_dict = get_stock_balance_for(item.item_code, item.warehouse,
				self.posting_date, self.posting_time, batch_no_craft=item.batch_no_craft)

			if (((item.qty is None or item.qty==item_dict.get("qty")) and
				(item.valuation_rate is None or item.valuation_rate==item_dict.get("rate")) and not item.serial_no_craft)):
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
				self.difference_amount += (flt(item.qty, item.precision("qty")) * \
					flt(item.valuation_rate or item_dict.get("rate"), item.precision("valuation_rate")) \
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
			frappe.msgprint(_("Removed items with no change in quantity or value."))

def get_stock_balance_for(item_code, warehouse,
	posting_date, posting_time, batch_no_craft=None, with_valuation_rate= True):
	frappe.has_permission("Stock Reconciliation", "write", throw = True)

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


def custom_on_submit(args,statuc):
	from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import StockReconciliation
	StockReconciliation.validate = custom_validate



frappe.ui.form.on("Stock Reconciliation", {
	onload: function(frm) {
		
		// end of life
		frm.set_query("item_code", "items", function(doc, cdt, cdn) {
			return {
				query: "erpnext.controllers.queries.item_query",
				filters:{
					"is_stock_item": 1
				}
			}
		});
	}
});


frappe.ui.form.on('Stock Reconciliation Item', {
  warehouse:function(frm, cdt, cdn) {
    var d = locals[cdt][cdn]
    frappe.call({
                                method: "stock_reco_serial.stock_reco_serial.stock_reco.get_serial_item_data",
                                args: {

                                        item_code: d.item_code,
                                        warehouse: d.warehouse,
                                        posting_date: frm.doc.posting_date,
                                        posting_time: frm.doc.posting_time,
					batch_no: d.batch_no
                                },
                                callback: function(r) {

                                        if(r.message){

                                                frappe.model.set_value(cdt,cdn,"avg_valuation_rate",r.message.valuation_rate)
                                                frappe.model.set_value(cdt, cdn, "current_serial_no_craft", r.message.serial_nos);
						frappe.model.set_value(cdt, cdn, "serial_no_craft", r.message.serial_nos);
						frappe.model.set_value(cdt,cdn,"valuation_rate",r.message.valuation_rate)
                                        }
                                }
                })

    
  },
  serial_no: function(frm, cdt, cdn) {
	var child = locals[cdt][cdn];

	if (child.serial_no_craft) {
		const serial_nos = child.serial_no_craft.trim().split('\n');
		frappe.model.set_value(cdt, cdn, "qty", serial_nos.length);
	}
  },
  item_code: function(frm, cdt, cdn) {

                var d = locals[cdt][cdn];
                frappe.call({
                                method: "stock_reco_serial.stock_reco_serial.stock_reco.get_serial_item_data",
                                args: {
                                        
					item_code: d.item_code,
					warehouse: d.warehouse,
					posting_date: frm.doc.posting_date,
					posting_time: frm.doc.posting_time,
					batch_no: d.batch_no
                                },
                                callback: function(r) {

                                        if(r.message){

                                                frappe.model.set_value(cdt,cdn,"avg_valuation_rate",r.message.valuation_rate)
						//frappe.model.set_value(cdt, cdn, "current_serial_no_craft", r.message.serial_nos);
                                        }
                                }
                })

  }

});

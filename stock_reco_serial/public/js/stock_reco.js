frappe.ui.form.on("Stock Reconciliation Item", {
	item_code: function(frm, cdt, cdn) {
	
		var d = locals[cdt][cdn];
		frappe.call({
				method: "stock_reco_serial.stock_reco_serial.stock_reco.get_serial_item_data",
				args: {
					item_code: d.item_code,
					
				},
				callback: function(r) {
				
					if(r.message){
						
						frappe.model.set_value(cdt,cdn,"avg_valuation_rate",r.message.valuation_rate)
						
					}
				}
		})
	}
});

frappe.ui.form.on('Stock Reconciliation Item', {
  warehouse:function(frm, cdt, cdn) {
    var item = locals[cdt][cdn]
    
    frappe.model.set_value(cdt,cdn,"valuation_rate",item.avg_valuation_rate)
    frappe.model.set_value(cdt,cdn,"serial_no_craft",item.current_serial_no_craft)



  },
});

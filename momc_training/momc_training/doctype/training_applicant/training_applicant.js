const TRACK_LABELS = {
	"IT End User Support": "دعم المستخدمين",
	Cybersecurity: "الأمن السيبراني",
	Programming: "البرمجة",
};

frappe.ui.form.on("Training Applicant", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (["Submitted", "Exam Completed", "Accepted", "Rejected"].includes(frm.doc.status)) {
			frm.add_custom_button(__("قبول"), () => decide(frm, "Accepted"), __("القرار"));
			frm.add_custom_button(__("رفض"), () => decide(frm, "Rejected"), __("القرار"));
		}
		if (frm.doc.exam_attempt) {
			frm.add_custom_button(__("نتيجة الامتحان"), () =>
				frappe.set_route("Form", "Training Exam Attempt", frm.doc.exam_attempt)
			);
		}
		if (frm.doc.ocr_corrected_fields) {
			frm.dashboard.set_headline_alert(
				`<div class="text-warning">${__("عدّل المتقدم حقولاً قرأها النظام من الهوية:")} ${frappe.utils.escape_html(
					frm.doc.ocr_corrected_fields
				)}</div>`
			);
		}
		show_documents(frm);
	},
});

function decide(frm, decision) {
	const fields = [];
	if (decision === "Accepted") {
		fields.push({
			fieldname: "track",
			fieldtype: "Select",
			label: __("المسار المعتمد"),
			reqd: 1,
			options: Object.keys(TRACK_LABELS).map((value) => ({ value, label: TRACK_LABELS[value] })),
			default: frm.doc.recommended_track || frm.doc.track_preference,
		});
	}
	fields.push({ fieldname: "notes", fieldtype: "Small Text", label: __("ملاحظات (تُرسل للمتقدم)") });

	const dialog = new frappe.ui.Dialog({
		title: decision === "Accepted" ? __("قبول المتقدم") : __("رفض المتقدم"),
		fields,
		primary_action_label: __("تأكيد وإرسال إشعار"),
		primary_action(values) {
			frappe.call({
				method: "momc_training.momc_training.doctype.training_applicant.training_applicant.decide",
				args: { name: frm.doc.name, decision, track: values.track, notes: values.notes },
				freeze: true,
				callback() {
					dialog.hide();
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}

function show_documents(frm) {
	const wrapper = frm.get_field("files_section")?.wrapper;
	if (!wrapper) return;
	$(wrapper).find(".momc-doc-previews").remove();
	const items = [
		["photo", "الصورة الشخصية"],
		["id_front", "الهوية - أمامي"],
		["id_back", "الهوية - خلفي"],
	].filter(([field]) => frm.doc[field]);
	if (!items.length) return;
	const html = items
		.map(
			([field, label]) => `
			<a href="${encodeURI(frm.doc[field])}" target="_blank" rel="noopener" style="text-align:center;display:inline-block;margin:0 0 12px 12px">
				<img src="${encodeURI(frm.doc[field])}" style="height:140px;border-radius:8px;border:1px solid var(--border-color)">
				<div class="text-muted small">${label}</div>
			</a>`
		)
		.join("");
	$(`<div class="momc-doc-previews" style="padding:12px 15px">${html}</div>`).appendTo(wrapper);
}

frappe.listview_settings["Training Applicant"] = {
	add_fields: ["status", "exam_total"],
	get_indicator(doc) {
		const map = {
			Draft: ["مسودة", "gray"],
			Submitted: ["أُرسل الطلب", "blue"],
			"Exam Completed": ["أنهى الامتحان", "purple"],
			Accepted: ["مقبول", "green"],
			Rejected: ["مرفوض", "red"],
			Withdrawn: ["منسحب", "darkgrey"],
		};
		const [label, color] = map[doc.status] || [doc.status, "gray"];
		return [label, color, `status,=,${doc.status}`];
	},
};

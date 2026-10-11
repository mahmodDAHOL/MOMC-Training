// Mark the programme's desk screens so desk.css can apply the ministry identity
// to them only — the rest of ERPNext keeps its own look.
(() => {
	const DOCTYPES = new Set([
		"Training Applicant",
		"Training Exam Attempt",
		"Training Exam Question",
		"Training Program Settings",
	]);
	const WORKSPACE = "تدريب الخريجين";

	function isOurs(route) {
		if (!route || !route.length) return false;
		if (route[0] === "Workspaces") return route[route.length - 1] === WORKSPACE;
		return DOCTYPES.has(route[1]);
	}

	function mark() {
		document.body.classList.toggle("momc-brand", isOurs(frappe.get_route()));
	}

	$(document).on("page-change", mark);
	$(document).ready(() => frappe.router && frappe.router.on && frappe.router.on("change", mark));
})();

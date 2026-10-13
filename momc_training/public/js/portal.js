/* MOMC graduate training portal — vanilla JS, no framework. */
(() => {
	"use strict";

	const API = "/api/method/momc_training.api.";
	const csrf = () => document.querySelector('meta[name="ta-csrf"]')?.content || "";
	const $ = (sel, root = document) => root.querySelector(sel);
	const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

	// ---------------------------------------------------------------- api ---
	function serverMessage(body) {
		try {
			if (body._server_messages) {
				const msgs = JSON.parse(body._server_messages).map((m) => {
					try { return JSON.parse(m).message; } catch { return m; }
				});
				const tmp = document.createElement("div");
				tmp.innerHTML = msgs.join(" ");
				return tmp.textContent.trim();
			}
		} catch { /* fall through */ }
		return "";
	}

	async function api(method, data = {}, { verb = "POST", file = null } = {}) {
		const opts = { method: verb, headers: { Accept: "application/json", "X-TA-CSRF": csrf() }, credentials: "same-origin" };
		let url = API + method;
		if (verb === "GET") {
			const qs = new URLSearchParams(data).toString();
			if (qs) url += "?" + qs;
		} else if (file) {
			const fd = new FormData();
			Object.entries(data).forEach(([k, v]) => fd.append(k, v));
			fd.append("file", file);
			opts.body = fd;
		} else {
			opts.headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8";
			opts.body = new URLSearchParams(
				Object.fromEntries(Object.entries(data).map(([k, v]) => [k, typeof v === "object" ? JSON.stringify(v) : v]))
			);
		}
		let res;
		try {
			res = await fetch(url, opts);
		} catch {
			throw new Error("تعذّر الاتصال بالخادم. تحقق من الإنترنت وحاول مجدداً.");
		}
		let body = {};
		try { body = await res.json(); } catch { /* non-JSON error page */ }
		if (!res.ok) {
			if (res.status === 401 || res.status === 403) {
				const msg = serverMessage(body) || "انتهت الجلسة، يرجى تسجيل الدخول من جديد.";
				if (res.status === 401) setTimeout(() => (location.href = "/training/login"), 1500);
				throw new Error(msg);
			}
			if (res.status === 429) throw new Error("محاولات كثيرة خلال وقت قصير. انتظر قليلاً ثم حاول.");
			throw new Error(serverMessage(body) || "حدث خطأ غير متوقع. حاول مجدداً.");
		}
		return body.message;
	}

	function show(el, text) {
		if (!el) return;
		el.textContent = text || "";
		el.classList.toggle("is-shown", Boolean(text));
	}

	async function busy(button, fn) {
		if (button) { button.disabled = true; button.classList.add("is-busy"); }
		try { return await fn(); } finally {
			if (button) { button.disabled = false; button.classList.remove("is-busy"); }
		}
	}

	// --------------------------------------------------------- auth forms ---
	const AUTH_FORMS = { register: "auth.register", login: "auth.login", verify: "auth.verify", forgot: "auth.forgot", reset: "auth.reset" };

	$$("form[data-form]").forEach((form) => {
		const method = AUTH_FORMS[form.dataset.form];
		if (!method) return;
		form.addEventListener("submit", async (event) => {
			event.preventDefault();
			const error = $("[data-error]", form);
			show(error, "");
			const invalid = $$("input[required]", form).find((i) => (i.type === "checkbox" ? !i.checked : !i.value.trim()));
			if (invalid) {
				show(error, invalid.type === "checkbox" ? "يجب الموافقة على سياسة استخدام البيانات." : "أكمل الحقول المطلوبة.");
				invalid.focus();
				return;
			}
			const data = Object.fromEntries(new FormData(form).entries());
			try {
				const r = await busy($('button[type="submit"]', form), () => api(method, data));
				if (r && r.next) location.href = r.next;
			} catch (e) {
				show(error, e.message);
			}
		});
	});

	$$('[data-action="resend"]').forEach((btn) =>
		btn.addEventListener("click", async () => {
			const form = btn.closest(".panel");
			try {
				const r = await busy(btn, () => api("auth.resend", { email: btn.dataset.email, purpose: btn.dataset.purpose }));
				show($("[data-info]", form), r.message);
				show($("[data-error]", form), "");
			} catch (e) {
				show($("[data-error]", form), e.message);
			}
		})
	);

	$$('[data-action="logout"]').forEach((btn) =>
		btn.addEventListener("click", async () => {
			try { await api("auth.logout"); } finally { location.href = "/training/login"; }
		})
	);

	// ------------------------------------------------------ profile wizard ---
	const wizard = $("[data-wizard]");
	if (wizard) initWizard(wizard);

	function initWizard(root) {
		const form = $('form[data-form="profile"]', root);
		const error = $("[data-error]", form);
		const info = $("[data-info]", form);
		const stepButtons = $$("[data-step]", root);
		let current = 1;

		const paneValues = (pane) => {
			const values = {};
			$$("input[name], select[name], textarea[name]", pane).forEach((el) => {
				if (el.type === "radio") { if (el.checked) values[el.name] = el.value; }
				else values[el.name] = el.value.trim();
			});
			$$('input[type="radio"]', pane).forEach((el) => { if (!(el.name in values)) values[el.name] = ""; });
			return values;
		};

		async function save(pane) {
			const values = paneValues(pane);
			if (!Object.keys(values).length) return true;
			if (values.national_id && !/^[0-9٠-٩]{11}$/.test(values.national_id)) {
				show(error, "الرقم الوطني يجب أن يتكون من 11 رقماً.");
				return false;
			}
			await api("profile.save", { data: values });
			return true;
		}

		async function go(step) {
			if (step === current) return;
			const pane = $(`[data-pane="${current}"]`, form);
			show(error, "");
			show(info, "");
			try {
				if (step > current && !(await save(pane))) return;
				else if (step < current) await save(pane).catch(() => true);
			} catch (e) {
				show(error, e.message);
				return;
			}
			stepButtons.forEach((b) => {
				const n = Number(b.dataset.step);
				b.toggleAttribute("aria-current", n === step);
				if (n === step) b.setAttribute("aria-current", "step");
				b.classList.toggle("is-done", n < step);
			});
			$$(".step-pane", form).forEach((p) => p.classList.toggle("is-active", Number(p.dataset.pane) === step));
			current = step;
			if (step === 5) buildReview();
			form.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
			$(`[data-pane="${step}"] h2`, form)?.focus?.();
		}

		stepButtons.forEach((b) => b.addEventListener("click", () => go(Number(b.dataset.step))));
		$$("[data-next]", form).forEach((b) => b.addEventListener("click", () => busy(b, () => go(current + 1))));
		$$("[data-prev]", form).forEach((b) => b.addEventListener("click", () => go(current - 1)));

		// Uploads (+ OCR for both ID sides)
		$$("[data-upload]", form).forEach((zone) => {
			const input = $('input[type="file"]', zone);
			const state = $(".dz-state", zone);
			input.addEventListener("change", async () => {
				const file = input.files[0];
				if (!file) return;
				const kind = zone.dataset.upload;
				show(error, "");
				zone.classList.add("is-busy");
				state.textContent = kind.startsWith("id_") ? "جارٍ الرفع وقراءة البيانات…" : "جارٍ الرفع…";
				if (file.type.startsWith("image/")) {
					let img = $("img.preview", zone);
					if (!img) { img = document.createElement("img"); img.className = "preview"; img.alt = ""; zone.prepend(img); }
					img.src = URL.createObjectURL(file);
				}
				try {
					const r = await api("files.upload", { kind }, { file });
					zone.classList.add("has-file");
					state.textContent = "تم الرفع — اضغط للاستبدال";
					if (r.ocr) applyOcr(r.ocr, kind);
				} catch (e) {
					state.textContent = "لم يُرفع الملف";
					show(error, e.message);
				} finally {
					zone.classList.remove("is-busy");
					input.value = "";
				}
			});
		});

		function applyOcr(ocr, kind) {
			if (ocr.status !== "ok") {
				show(info, "رُفعت الصورة، لكن تعذّرت قراءتها آلياً. أدخل بياناتك يدوياً في الخطوة التالية.");
				return;
			}
			const expected = kind === "id_front" ? "front" : "back";
			if (ocr.side && ocr.side !== expected) {
				show(error, expected === "front"
					? "يبدو أن هذه صورة الوجه الخلفي. ارفع هنا الوجه الذي يحمل الصورة الشخصية."
					: "يبدو أن هذه صورة الوجه الأمامي. ارفع هنا الوجه الذي يحمل الأمانة والقيد.");
			}
			const filled = [];
			Object.entries(ocr.fields || {}).forEach(([name, value]) => {
				const el = $(`[name="${name}"]`, form);
				if (!el || !value) return;
				el.value = value;
				el.classList.add("from-ocr");
				// Low confidence: the two readers disagreed or the label was not found.
				el.classList.toggle("ocr-check", (ocr.confidence || {})[name] < 0.7);
				filled.push(name);
			});
			show(info, filled.length
				? `قرأنا ${filled.length} حقلاً من الهوية. راجعها في الخطوة التالية وصحّح أي خطأ.`
				: "رُفعت الصورة، لكن لم نتمكن من قراءة حقول منها. تأكد أن البطاقة واضحة وتملأ الإطار، أو أدخل البيانات يدوياً.");
		}
		$$(".input", form).forEach((el) => el.addEventListener("input", () => el.classList.remove("from-ocr", "ocr-check")));

		function buildReview() {
			const dl = $("[data-review]", form);
			const rows = [];
			const labelOf = (el) => (el.labels && el.labels[0] ? el.labels[0].textContent.trim() : el.name);
			$$('input.input[name], select.input[name], textarea.input[name]', form).forEach((el) => {
				const value = el.tagName === "SELECT" ? el.options[el.selectedIndex]?.text : el.value;
				rows.push([labelOf(el), value]);
			});
			const track = $('input[name="track_preference"]:checked', form);
			rows.push(["المسار المرغوب", track ? track.parentElement.textContent.trim() : ""]);
			$$("[data-upload]", form).forEach((zone) =>
				rows.push([$(".dz-label strong", zone).textContent + " (" + zone.closest("section").querySelector("h2").textContent + ")",
					zone.classList.contains("has-file") ? "مرفوع" : ""])
			);
			dl.replaceChildren(
				...rows.flatMap(([k, v]) => {
					const dt = document.createElement("dt"); dt.textContent = k;
					const dd = document.createElement("dd");
					if (v) dd.textContent = v; else { dd.textContent = "غير مُدخل"; dd.className = "missing"; }
					return [dt, dd];
				})
			);
		}

		$('[data-action="submit-profile"]', form)?.addEventListener("click", async (event) => {
			show(error, "");
			try {
				const r = await busy(event.currentTarget, () => api("profile.submit"));
				location.href = r.next;
			} catch (e) {
				show(error, e.message);
			}
		});
	}

	// ---------------------------------------------------------------- exam ---
	const exam = $("[data-exam]");
	if (exam) initExam(exam);

	function initExam(root) {
		const intro = $("[data-exam-intro]", root);
		const run = $("[data-exam-run]", root);
		const runError = $("[data-error]", run);
		let questions = [];
		let index = 0;
		let deadline = 0;
		let timerId = null;
		let submitting = false;

		const answered = () => questions.filter((q) => q.picked !== null && q.picked !== undefined).length;

		function render() {
			const q = questions[index];
			$("[data-section]", run).textContent = `${q.section_label || q.section} — السؤال ${index + 1} من ${questions.length}`;
			$("[data-question]", run).textContent = q.text;
			const box = $("[data-options]", run);
			box.replaceChildren(
				...q.options.map((text, i) => {
					const label = document.createElement("label");
					label.className = "option";
					const input = document.createElement("input");
					input.type = "radio";
					input.name = "choice";
					input.value = String(i);
					input.checked = q.picked === i;
					input.addEventListener("change", () => pick(i));
					label.append(input, document.createTextNode(" " + text));
					return label;
				})
			);
			$("[data-q-prev]", run).disabled = index === 0;
			$("[data-q-next]", run).disabled = index === questions.length - 1;
			renderNavigator();
		}

		function renderNavigator() {
			const nav = $("[data-navigator]", run);
			nav.replaceChildren(
				...questions.map((q, i) => {
					const b = document.createElement("button");
					b.type = "button";
					b.textContent = String(i + 1);
					b.setAttribute("aria-label", `السؤال ${i + 1}${q.picked !== null && q.picked !== undefined ? " (مُجاب)" : ""}`);
					if (q.picked !== null && q.picked !== undefined) b.classList.add("is-answered");
					if (i === index) b.setAttribute("aria-current", "true");
					b.addEventListener("click", () => { index = i; render(); });
					return b;
				})
			);
			$("[data-count]", run).textContent = `أجبت عن ${answered()} من ${questions.length}`;
			$("[data-progress]", run).style.width = `${(answered() / questions.length) * 100}%`;
		}

		async function pick(i) {
			const q = questions[index];
			const previous = q.picked;
			q.picked = i;
			renderNavigator();
			show(runError, "");
			try {
				await api("exam.answer", { question: q.id, choice: i });
			} catch (e) {
				q.picked = previous;
				render();
				show(runError, "لم تُحفظ الإجابة: " + e.message);
			}
		}

		function tick() {
			const left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
			const m = String(Math.floor(left / 60)).padStart(2, "0");
			const s = String(left % 60).padStart(2, "0");
			const timer = $("[data-timer]", run);
			timer.textContent = `${m}:${s}`;
			timer.classList.toggle("is-low", left <= 300);
			if (left === 300) show(runError, "بقيت 5 دقائق.");
			if (left <= 0) finish(true);
		}

		function begin(payload) {
			if (!payload || !payload.questions) { location.href = "/training/status"; return; }
			questions = payload.questions;
			deadline = Date.now() + payload.seconds_left * 1000;
			index = Math.max(0, questions.findIndex((q) => q.picked === null || q.picked === undefined));
			intro.hidden = true;
			run.hidden = false;
			render();
			tick();
			timerId = setInterval(tick, 1000);
			window.addEventListener("beforeunload", warnLeave);
		}

		function warnLeave(e) { if (!submitting) { e.preventDefault(); e.returnValue = ""; } }

		async function finish(auto) {
			if (submitting) return;
			if (!auto) {
				const missing = questions.length - answered();
				const msg = missing ? `لم تجب عن ${missing} سؤالاً. هل تريد التسليم الآن؟` : "هل تريد تسليم الامتحان؟ لن تتمكن من تعديل إجاباتك.";
				if (!confirm(msg)) return;
			}
			submitting = true;
			clearInterval(timerId);
			try {
				const r = await api("exam.submit");
				location.href = r.next;
			} catch (e) {
				submitting = false;
				show(runError, "تعذّر تسليم الامتحان. إجاباتك محفوظة، حاول التسليم مجدداً. " + e.message);
			}
		}

		$('[data-action="start-exam"]', root)?.addEventListener("click", async (event) => {
			if (!confirm("سيبدأ المؤقت الآن ولن يتوقف. هل أنت مستعد؟")) return;
			try {
				begin(await busy(event.currentTarget, () => api("exam.start")));
			} catch (e) {
				show($("[data-error]", intro), e.message);
			}
		});
		$("[data-q-prev]", run).addEventListener("click", () => { if (index > 0) { index--; render(); } });
		$("[data-q-next]", run).addEventListener("click", () => { if (index < questions.length - 1) { index++; render(); } });
		$('[data-action="submit-exam"]', run).addEventListener("click", () => finish(false));

		if (root.dataset.inProgress === "1") {
			api("exam.state", {}, { verb: "GET" }).then(begin).catch((e) => show($("[data-error]", intro), e.message));
		}
	}
})();

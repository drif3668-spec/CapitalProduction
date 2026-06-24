document.querySelectorAll(".flash").forEach((flash) => {
    setTimeout(() => flash.remove(), 4500);
});

document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", () => {
        const button = form.querySelector("button[type='submit'], button:not([type])");
        if (button && !button.dataset.keepText) {
            button.dataset.original = button.textContent;
            button.textContent = "جاري الإرسال...";
        }
    });
});

document.querySelectorAll(".pick-card input").forEach((input) => {
    const updatePlanInfo = () => {
        const card = input.closest(".pick-card");
        const name = document.querySelector("#planInfoName");
        const price = document.querySelector("#planInfoPrice");
        const features = document.querySelector("#planInfoFeatures");
        if (!card || !name || !price || !features) return;
        name.textContent = (card.dataset.card || input.value).toUpperCase();
        price.textContent = card.dataset.price || "";
        features.innerHTML = (card.dataset.features || "")
            .split("|")
            .filter(Boolean)
            .map((feature) => `<li>${feature}</li>`)
            .join("");
    };
    input.addEventListener("change", () => {
        document.querySelectorAll(".pick-card").forEach((card) => card.classList.remove("selected"));
        input.closest(".pick-card").classList.add("selected");
        updatePlanInfo();
    });
    if (input.checked) {
        input.closest(".pick-card").classList.add("selected");
        updatePlanInfo();
    }
});

/* ─── Web3 Pricing Card Interaction ─── */
document.querySelectorAll("#pricing [data-plan]").forEach((card) => {
    card.addEventListener("click", () => {
        document.querySelectorAll("#pricing [data-plan]").forEach((item) => {
            item.classList.remove("web3-plan-active");
        });
        card.classList.add("web3-plan-active");
    });
});

const withdrawMethod = document.querySelector("#withdrawMethod");
if (withdrawMethod) {
    withdrawMethod.addEventListener("change", () => {
        if (withdrawMethod.value === "__local__") {
            window.location.href = withdrawMethod.dataset.localUrl;
        }
    });
}

document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
        const target = document.getElementById(button.dataset.copyTarget);
        if (!target) return;
        await navigator.clipboard.writeText(target.value);
        button.textContent = "تم النسخ";
        setTimeout(() => { button.textContent = "نسخ رمز التذكرة"; }, 1800);
    });
});

const activities = [
    "عميل من الجزائر قام بإيداع",
    "عميل من مصر قام بسحب",
    "عميل من فرنسا قام بتحديث محفظته",
    "نشاط إيداع من المغرب",
    "طلب ربط من السعودية",
    "تحديث محفظة من الهند",
    "طلب سحب من تونس",
    "نشاط حساب من بريطانيا",
];
document.querySelectorAll("[data-live-activity]").forEach((node) => {
    let index = 0;
    setInterval(() => {
        index = (index + 1) % activities.length;
        node.style.opacity = "0";
        setTimeout(() => {
            node.textContent = activities[index];
            node.style.opacity = "1";
        }, 180);
    }, 1000);
});

document.querySelectorAll("[data-counter]").forEach((node) => {
    const target = Number(node.dataset.counter);
    let value = 0;
    const step = Math.max(1, Math.ceil(target / 80));
    const timer = setInterval(() => {
        value += step;
        if (value >= target) {
            value = target;
            clearInterval(timer);
        }
        node.textContent = `+${value.toLocaleString("en-US")}`;
    }, 24);
});

const languageToggle = document.querySelector("[data-language-toggle]");
const translations = {
    ar: {
        "nav.home": "الرئيسية",
        "nav.cards": "البطاقات",
        "nav.referral": "برنامج الإحالة",
        "nav.support": "الدعم",
        "nav.quickLink": "الربط السريع",
        "buttons.signIn": "تسجيل الدخول",
        "buttons.getStarted": "ابدأ الآن",
        "buttons.viewClients": "عرض العملاء",
        "buttons.choosePlan": "اختر البطاقة",
    },
    en: {
        "nav.home": "Home",
        "nav.cards": "Cards",
        "nav.referral": "Referral Program",
        "nav.support": "Support",
        "nav.quickLink": "Quick Link",
        "buttons.signIn": "Sign In",
        "buttons.getStarted": "Get Started",
        "buttons.viewClients": "View Clients",
        "buttons.choosePlan": "Choose Your Plan",
    },
};

const applyLanguage = (lang) => {
    const activeLang = translations[lang] ? lang : "en";
    document.documentElement.lang = activeLang;
    document.documentElement.dir = activeLang === "ar" ? "rtl" : "ltr";
    document.querySelectorAll("[data-i18n]").forEach((node) => {
        const value = translations[activeLang][node.dataset.i18n];
        if (value) node.textContent = value;
    });
    document.querySelectorAll(".language-option").forEach((option) => {
        option.classList.toggle("active", option.dataset.lang === activeLang);
    });
};

if (languageToggle) {
    const globeButton = languageToggle.querySelector(".globe-language-button");
    const savedLanguage = localStorage.getItem("trbridgo-language") || "en";
    applyLanguage(savedLanguage);

    globeButton.addEventListener("click", (event) => {
        event.stopPropagation();
        const isOpen = languageToggle.classList.toggle("open");
        globeButton.setAttribute("aria-expanded", String(isOpen));
    });

    languageToggle.querySelectorAll(".language-option").forEach((option) => {
        option.addEventListener("click", () => {
            const lang = option.dataset.lang;
            localStorage.setItem("trbridgo-language", lang);
            applyLanguage(lang);
            languageToggle.classList.remove("open");
            globeButton.setAttribute("aria-expanded", "false");
        });
    });

    document.addEventListener("click", () => {
        languageToggle.classList.remove("open");
        globeButton.setAttribute("aria-expanded", "false");
    });
}

const heroTypewriterText = document.querySelector("[data-hero-typewriter]");
if (heroTypewriterText) {
    const typewriterValue = heroTypewriterText.dataset.heroTypewriter || heroTypewriterText.textContent.trim();
    const typewriterChars = Array.from(typewriterValue);
    const typeSpeed = 58;
    const holdTime = 2000;
    const fadeTime = 520;

    const runHeroTypewriter = () => {
        let index = 0;
        heroTypewriterText.classList.remove("is-fading");
        heroTypewriterText.textContent = "";

        const timer = setInterval(() => {
            heroTypewriterText.textContent += typewriterChars[index] || "";
            index += 1;
            if (index >= typewriterChars.length) {
                clearInterval(timer);
                setTimeout(() => {
                    heroTypewriterText.classList.add("is-fading");
                    setTimeout(runHeroTypewriter, fadeTime);
                }, holdTime);
            }
        }, typeSpeed);
    };

    runHeroTypewriter();
}

const siteInfinityLogos = document.querySelectorAll(".site-infinity-logo-wrap");
if (siteInfinityLogos.length) {
    const updateSiteLogoReflection = () => {
        const shift = Math.round((window.scrollY % 360) * 0.28);
        siteInfinityLogos.forEach((logo) => logo.style.setProperty("--site-logo-shift", `${shift}deg`));
    };
    updateSiteLogoReflection();
    window.addEventListener("scroll", updateSiteLogoReflection, { passive: true });
}

/* ── Support Widget v3 ──────────────────────────────────── */
document.querySelectorAll("[data-rich-support]").forEach((widget) => {
    const toggleBtns = widget.querySelectorAll("[data-support-toggle]");
    const muteBtn    = widget.querySelector("[data-support-mute]");
    const form       = widget.querySelector("[data-support-form]");
    const thread     = widget.querySelector("[data-support-thread]");
    const identity   = widget.querySelector("[data-sw-identity]");

    let audioCtx = null;
    let muted = false;
    let lastReplyCount = 0;
    let pollTimer = null;
    let messageSent = false;

    const esc = (v) => String(v || "")
        .replace(/&/g,"&amp;").replace(/</g,"&lt;")
        .replace(/>/g,"&gt;").replace(/"/g,"&quot;");

    /* Soft chime — plays only when agent replies arrive */
    const playChime = () => {
        if (muted) return;
        try {
            audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
            const osc  = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.type = "sine";
            osc.frequency.setValueAtTime(880, audioCtx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(660, audioCtx.currentTime + 0.18);
            gain.gain.setValueAtTime(0.055, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.45);
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start();
            osc.stop(audioCtx.currentTime + 0.45);
        } catch (_) {}
    };

    const renderMessages = (messages, checkSound = false) => {
        if (!thread) return;
        let replyCount = 0;
        if (!messages.length) {
            thread.innerHTML = `<div class="sw-bubble sw-agent sw-intro">
                <span class="sw-agent-avatar">💬</span>
                <div class="sw-bubble-body">أهلاً بك في <b>TrBridgo.io</b><br>
                فريقنا جاهز لمساعدتك في ربط حسابات MT4 و MT5.</div>
            </div>`;
            return;
        }
        thread.innerHTML = messages.map((msg) => {
            const replies = (msg.replies || []).map((r) => {
                replyCount++;
                const avatar = r.agent_image
                    ? `<img src="${esc(r.agent_image)}" alt="">`
                    : "🤝";
                const time = (r.created_at || "").slice(11, 16);
                return `<div class="sw-bubble sw-agent">
                    <span class="sw-agent-avatar">${avatar}</span>
                    <div class="sw-bubble-body">
                        <span class="sw-agent-name">${esc(r.agent_name || "TrBridgo Support")}</span>
                        ${esc(r.text)}
                        <span class="sw-time">${time}</span>
                    </div>
                </div>`;
            }).join("");
            const statusClass = `sw-status-${(msg.status || "").replace(/\s+/g, "-")}`;
            const time = (msg.created_at || "").slice(11, 16);
            return `<div class="sw-bubble sw-user">
                <div class="sw-bubble-body">
                    ${esc(msg.message)}
                    <span class="sw-status-tag ${statusClass}">${esc(msg.status || "جديدة")}</span>
                    <span class="sw-time">${time}</span>
                </div>
            </div>${replies}`;
        }).join("");
        thread.scrollTop = thread.scrollHeight;
        if (checkSound && replyCount > lastReplyCount) playChime();
        lastReplyCount = replyCount;
    };

    const loadMessages = async (checkSound = false) => {
        try {
            const res  = await fetch("/support/messages", { headers: { Accept: "application/json" } });
            const data = await res.json();
            if (data.ok) renderMessages(data.messages || [], checkSound);
        } catch (_) {}
    };

    const startPolling = () => {
        if (pollTimer) return;
        pollTimer = setInterval(() => loadMessages(true), 8000);
    };
    const stopPolling = () => { clearInterval(pollTimer); pollTimer = null; };

    /* Open / close */
    toggleBtns.forEach((btn) => btn.addEventListener("click", async () => {
        const opening = !widget.classList.contains("open");
        widget.classList.toggle("open", opening);
        widget.querySelector("[data-support-window]")?.setAttribute("aria-hidden", String(!opening));
        btn.setAttribute("aria-expanded", String(opening));
        if (opening) { await loadMessages(false); startPolling(); }
        else          { stopPolling(); }
    }));

    /* Mute toggle */
    muteBtn?.addEventListener("click", () => {
        muted = !muted;
        muteBtn.dataset.muted = muted ? "1" : "0";
        muteBtn.setAttribute("title", muted ? "تفعيل الصوت" : "كتم الصوت");
        muteBtn.textContent = muted ? "🔇" : "🔔";
    });

    /* Send message */
    form?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const msg = form.message?.value.trim();
        if (!msg) return;
        try {
            const res = await fetch("/support/messages", {
                method: "POST",
                headers: { "Content-Type": "application/json", Accept: "application/json" },
                body: JSON.stringify({
                    message: msg,
                    guest_name:  form.guest_name?.value.trim()  || "",
                    guest_email: form.guest_email?.value.trim() || "",
                }),
            });
            const data = await res.json();
            if (data.ok) {
                form.message.value = "";
                /* Hide identity section after first successful send */
                if (!messageSent && identity) {
                    identity.style.display = "none";
                    messageSent = true;
                }
                await loadMessages(false);
            }
        } catch (_) {}
    });

    /* Auto-textarea height */
    form?.querySelector(".sw-textarea")?.addEventListener("input", function () {
        this.style.height = "auto";
        this.style.height = Math.min(this.scrollHeight, 120) + "px";
    });

    if (widget.classList.contains("support-center-panel")) loadMessages(false);
});

document.querySelectorAll("[data-open-client-support]").forEach((button) => {
    button.addEventListener("click", () => {
        const w = document.querySelector("[data-rich-support]");
        const t = w?.querySelector("[data-support-toggle]");
        if (!w || !t) return;
        if (!w.classList.contains("open")) t.click();
        else w.querySelector("[data-support-thread]")?.scrollTo({ top: 99999, behavior: "smooth" });
    });
});

/* ── Admin Support Inbox ────────────────────────────────── */
(function initAdminInbox() {
    const inbox = document.getElementById("adminInbox");
    if (!inbox) return;

    const items      = inbox.querySelectorAll(".inbox-item");
    const detail     = document.getElementById("inboxDetail");
    const searchInput = document.getElementById("inboxSearch");
    const filterSel  = document.getElementById("inboxFilter");

    const modeLabels = { human: "👤 Human", faq: "📋 FAQ Agent", ai: "🤖 AI Agent" };
    const modeDots   = { human: "am-human", faq: "am-faq", ai: "am-ai" };

    /* Show conversation */
    const openConv = (id) => {
        items.forEach((el) => el.classList.toggle("active", el.dataset.inboxId === id));
        detail.querySelectorAll(".inbox-conv").forEach((c) => { c.hidden = c.dataset.conv !== id; });
        const placeholder = detail.querySelector(".inbox-placeholder");
        if (placeholder) placeholder.hidden = true;

        /* Scroll thread to bottom */
        const thread = detail.querySelector(`#conv-${id} .inbox-thread`);
        if (thread) thread.scrollTop = thread.scrollHeight;
    };

    items.forEach((item) => {
        item.addEventListener("click", () => openConv(item.dataset.inboxId));
    });

    /* Search + filter */
    const filterItems = () => {
        const q      = (searchInput?.value || "").toLowerCase();
        const status = (filterSel?.value || "");
        items.forEach((item) => {
            const nameMatch    = item.dataset.inboxName?.toLowerCase().includes(q);
            const previewMatch = item.dataset.inboxPreview?.toLowerCase().includes(q);
            const statusMatch  = !status || item.dataset.inboxStatus === status;
            item.style.display = (nameMatch || previewMatch) && statusMatch ? "" : "none";
        });
    };
    searchInput?.addEventListener("input", filterItems);
    filterSel?.addEventListener("change", filterItems);

    /* Agent mode selectors */
    inbox.querySelectorAll("[data-mode-select]").forEach((sel) => {
        const convId    = sel.dataset.modeSelect;
        const labelEl   = document.getElementById(`am-label-${convId}`);
        const modeInput = document.querySelector(`[data-reply-form="${convId}"] .inbox-reply-mode-input`);

        sel.addEventListener("change", () => {
            const mode = sel.value;
            if (labelEl) {
                const dot = `<span class="agent-mode-dot ${modeDots[mode] || "am-human"}"></span>`;
                labelEl.innerHTML = `${dot}${modeLabels[mode] || "Human"}`;
            }
            if (modeInput) modeInput.value = mode;
        });
    });

    /* AJAX reply forms */
    inbox.querySelectorAll("[data-reply-form]").forEach((replyForm) => {
        const msgId     = replyForm.dataset.replyForm;
        const statusEl  = replyForm.querySelector("[data-reply-status]");
        const sendBtn   = replyForm.querySelector(".inbox-reply-send");

        replyForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const text      = replyForm.querySelector(".inbox-reply-textarea")?.value.trim();
            const agentId   = replyForm.querySelector(".inbox-agent-select")?.value || "";
            const replyMode = replyForm.querySelector(".inbox-reply-mode-input")?.value || "human";
            if (!text) return;

            if (sendBtn) { sendBtn.disabled = true; sendBtn.style.opacity = ".6"; }
            try {
                const res = await fetch(`/admin/support-message/${msgId}/reply`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", Accept: "application/json" },
                    body: JSON.stringify({ reply_text: text, agent_id: agentId, reply_mode: replyMode }),
                });
                const data = await res.json();
                if (data.ok) {
                    replyForm.querySelector(".inbox-reply-textarea").value = "";
                    if (statusEl) { statusEl.textContent = "تم إرسال الرد"; }
                    /* Append reply bubble to thread immediately */
                    const thread = document.querySelector(`#conv-${msgId} .inbox-thread`);
                    if (thread) {
                        const bubble = document.createElement("div");
                        bubble.className = "inbox-bubble inbox-bubble-agent";
                        bubble.innerHTML = `
                            <div class="inbox-bubble-meta">
                                <span class="inbox-agent-avatar-letter">🤝</span>
                                <span class="inbox-bubble-agent-name">TrBridgo Support</span>
                            </div>
                            <div class="inbox-bubble-body">${text.replace(/</g,"&lt;")}</div>
                            <span class="inbox-bubble-time">${new Date().toTimeString().slice(0,5)}</span>`;
                        thread.appendChild(bubble);
                        thread.scrollTop = thread.scrollHeight;
                    }
                    /* Update list item badge to تم الرد */
                    const listItem = inbox.querySelector(`[data-inbox-id="${msgId}"]`);
                    if (listItem) {
                        listItem.classList.remove("inbox-unread");
                        listItem.dataset.inboxStatus = "تم الرد";
                        const badge = listItem.querySelector(".inbox-item-badge");
                        if (badge) { badge.className = "inbox-item-badge inbox-badge-تم-الرد"; badge.textContent = "تم الرد"; }
                    }
                    setTimeout(() => { if (statusEl) statusEl.textContent = ""; }, 3000);
                } else {
                    if (statusEl) statusEl.textContent = data.error || "حدث خطأ";
                }
            } catch (_) {
                if (statusEl) statusEl.textContent = "تعذّر الإرسال";
            } finally {
                if (sendBtn) { sendBtn.disabled = false; sendBtn.style.opacity = ""; }
            }
        });
    });
}());

document.querySelectorAll("[data-platform-picker]").forEach((picker) => {
    const form = document.querySelector("#quick-form");
    const select = form?.querySelector("[data-platform-select]");
    const submitLabel = form?.querySelector("[data-platform-submit]");
    const applyPlatform = (platform) => {
        picker.querySelectorAll("[data-platform]").forEach((card) => {
            card.classList.toggle("active", card.dataset.platform === platform);
        });
        if (select) select.value = platform;
        if (submitLabel) submitLabel.textContent = platform;
        form?.scrollIntoView({ behavior: "smooth", block: "center" });
    };
    picker.querySelectorAll("[data-platform]").forEach((card) => {
        card.addEventListener("click", () => applyPlatform(card.dataset.platform || "MT5"));
    });
    select?.addEventListener("change", () => applyPlatform(select.value));
});

document.querySelectorAll("[data-marketing-dialog-open]").forEach((button) => {
    const targetName = button.dataset.marketingDialogOpen;
    const dialog = document.querySelector(`[data-marketing-dialog="${targetName}"]`);
    button.addEventListener("click", () => {
        if (!dialog) return;
        if (typeof dialog.showModal === "function") {
            dialog.showModal();
        } else {
            dialog.setAttribute("open", "open");
        }
    });
});

document.querySelectorAll("[data-marketing-dialog-close]").forEach((button) => {
    button.addEventListener("click", () => {
        const dialog = button.closest("[data-marketing-dialog]");
        if (!dialog) return;
        if (typeof dialog.close === "function") dialog.close();
        else dialog.removeAttribute("open");
    });
});

document.querySelectorAll("[data-marketing-dialog]").forEach((dialog) => {
    dialog.addEventListener("click", (event) => {
        if (event.target !== dialog) return;
        if (typeof dialog.close === "function") dialog.close();
        else dialog.removeAttribute("open");
    });
});

const marketingForm = document.querySelector("[data-marketing-form]");
if (marketingForm) {
    const formatRange = (min, max) => `${Math.max(0, Math.round(min)).toLocaleString()} - ${Math.max(0, Math.round(max)).toLocaleString()}`;
    const updateMarketingEstimates = () => {
        const selectedCountries = marketingForm.querySelectorAll('input[name="countries"]:checked').length || 1;
        const selectedBudget = marketingForm.querySelector('input[name="budget"]:checked');
        let budget = Number(selectedBudget?.value || 10);
        if (selectedBudget?.value === "custom") {
            budget = Number(marketingForm.querySelector('input[name="custom_budget"]')?.value || 0);
        }
        const duration = Number(marketingForm.querySelector('select[name="duration_days"]')?.value || 3);
        const durationFactor = Math.max(0.65, duration / 7);
        const reachMin = budget * 280 * selectedCountries * durationFactor;
        const reachMax = budget * 760 * selectedCountries * durationFactor;
        const clickMin = Math.max(1, reachMin * 0.028);
        const clickMax = Math.max(clickMin + 1, reachMax * 0.072);
        const leadMin = Math.max(1, clickMin * 0.12);
        const leadMax = Math.max(leadMin + 1, clickMax * 0.32);
        const conversionMin = 2 + Math.min(1.2, budget / 1000);
        const conversionMax = 5 + Math.min(2.0, selectedCountries * 0.15);
        marketingForm.querySelector("[data-estimated-reach]").textContent = formatRange(reachMin, reachMax);
        marketingForm.querySelector("[data-estimated-clicks]").textContent = formatRange(clickMin, clickMax);
        marketingForm.querySelector("[data-expected-leads]").textContent = formatRange(leadMin, leadMax);
        marketingForm.querySelector("[data-estimated-conversion]").textContent = `${conversionMin.toFixed(1)}% - ${conversionMax.toFixed(1)}%`;
    };
    marketingForm.addEventListener("input", updateMarketingEstimates);
    marketingForm.addEventListener("change", updateMarketingEstimates);
    updateMarketingEstimates();
}

document.querySelectorAll("[data-count-to]").forEach((counter) => {
    const target = Number(counter.dataset.countTo || 0);
    const prefix = counter.dataset.countPrefix || "";
    const suffix = counter.dataset.countSuffix || "";
    const decimals = String(counter.dataset.countTo || "").includes(".") ? 2 : 0;
    const duration = 950;
    let started = false;
    const runCounter = () => {
        if (started) return;
        started = true;
        const startTime = performance.now();
        const tick = (now) => {
            const progress = Math.min(1, (now - startTime) / duration);
            const eased = 1 - Math.pow(1 - progress, 3);
            const value = target * eased;
            counter.textContent = `${prefix}${value.toLocaleString(undefined, {
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals,
            })}${suffix}`;
            if (progress < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
    };
    if ("IntersectionObserver" in window) {
        const observer = new IntersectionObserver((entries) => {
            if (entries.some((entry) => entry.isIntersecting)) {
                runCounter();
                observer.disconnect();
            }
        }, { threshold: 0.25 });
        observer.observe(counter);
    } else {
        runCounter();
    }
});

document.querySelectorAll("[data-admin-section]").forEach((section) => {
    const table = section.querySelector("[data-admin-table]");
    const search = section.querySelector("[data-admin-search]");
    const status = section.querySelector("[data-admin-status]");
    const sort = section.querySelector("[data-admin-sort]");
    if (!table) return;
    const tbody = table.tBodies[0];
    const rows = Array.from(tbody.querySelectorAll("tr"));

    const applyFilters = () => {
        const query = (search?.value || "").trim().toLowerCase();
        const selectedStatus = status?.value || "";
        rows.forEach((row) => {
            const matchesSearch = !query || row.textContent.toLowerCase().includes(query);
            const matchesStatus = !selectedStatus || row.dataset.status === selectedStatus;
            row.style.display = matchesSearch && matchesStatus ? "" : "none";
        });
    };

    search?.addEventListener("input", applyFilters);
    status?.addEventListener("change", applyFilters);
    sort?.addEventListener("click", () => {
        rows.sort((a, b) => (b.dataset.date || "").localeCompare(a.dataset.date || ""));
        rows.forEach((row) => tbody.appendChild(row));
        applyFilters();
    });
});

/* ─── V2 NAV: Hamburger toggle ─── */
document.addEventListener("DOMContentLoaded", () => {
    const navToggle = document.querySelector("[data-nav-toggle]");
    const mobileMenu = document.querySelector("[data-mobile-menu]");
    if (navToggle && mobileMenu) {
        navToggle.addEventListener("click", () => {
            const open = navToggle.getAttribute("aria-expanded") === "true";
            navToggle.setAttribute("aria-expanded", String(!open));
            mobileMenu.classList.toggle("open", !open);
            mobileMenu.setAttribute("aria-hidden", String(open));
        });
        mobileMenu.querySelectorAll("a").forEach((link) => {
            link.addEventListener("click", () => {
                navToggle.setAttribute("aria-expanded", "false");
                mobileMenu.classList.remove("open");
                mobileMenu.setAttribute("aria-hidden", "true");
            });
        });
    }
});

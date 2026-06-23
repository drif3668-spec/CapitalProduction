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

document.querySelectorAll("[data-rich-support]").forEach((supportWidget) => {
    const toggles = supportWidget.querySelectorAll("[data-support-toggle]");
    const soundToggle = supportWidget.querySelector("[data-support-sound]");
    const form = supportWidget.querySelector("[data-support-form]");
    const thread = supportWidget.querySelector("[data-support-thread]");
    const statusNode = supportWidget.querySelector("[data-support-status]");
    let audioContext = null;
    let soundEnabled = true;
    let soundTimer = null;

    const escapeHtml = (value) => String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

    const beep = () => {
        if (!soundEnabled) return;
        try {
            audioContext = audioContext || new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gain = audioContext.createGain();
            oscillator.frequency.value = 740;
            gain.gain.value = 0.018;
            oscillator.connect(gain);
            gain.connect(audioContext.destination);
            oscillator.start();
            oscillator.stop(audioContext.currentTime + 0.08);
        } catch (_error) {
            soundEnabled = false;
        }
    };

    const startSound = () => {
        if (soundTimer || !soundEnabled) return;
        beep();
        soundTimer = setInterval(beep, 5000);
    };

    const renderMessages = (messages) => {
        if (!thread) return;
        if (!messages.length) {
            thread.innerHTML = supportWidget.classList.contains("home-support-widget")
                ? `<div class="support-bubble agent support-intro">أهلاً بك في <b>TrBridgo.io</b> 🌿<br>نقدّم خدمة متكاملة لربط حسابات التداول MT4 و MT5. اكتب رسالتك وسيردّ عليك أحد أعضاء الفريق.</div>`
                : `<div class="support-bubble agent">مرحبًا، اكتب استفسارك وسنرد عليك قريبًا.</div>`;
            return;
        }
        thread.innerHTML = messages.map((message) => {
            const replies = (message.replies || []).map((reply) => `
                <div class="support-bubble agent">
                    <div class="support-agent-line">
                        ${reply.agent_image ? `<img src="${escapeHtml(reply.agent_image)}" alt="">` : ""}
                        <span>${escapeHtml(reply.agent_name || "TrBridgo Support")}</span>
                    </div>
                    ${escapeHtml(reply.text)}
                </div>
            `).join("");
            return `
                <div class="support-bubble user">
                    ${escapeHtml(message.message)}
                    <small class="support-message-status">${escapeHtml(message.status || "جديدة")}</small>
                </div>
                ${replies}
            `;
        }).join("");
        thread.scrollTop = thread.scrollHeight;
    };

    const loadMessages = async () => {
        const response = await fetch("/support/messages", { headers: { "Accept": "application/json" } });
        const data = await response.json();
        if (data.ok) renderMessages(data.messages || []);
    };

    toggles.forEach((toggle) => toggle.addEventListener("click", async () => {
        supportWidget.classList.toggle("open");
        if (supportWidget.classList.contains("open")) {
            startSound();
            await loadMessages();
        }
    }));

    soundToggle?.addEventListener("click", () => {
        soundEnabled = !soundEnabled;
        soundToggle.textContent = soundEnabled ? "الصوت: تشغيل" : "الصوت: إيقاف";
        if (!soundEnabled && soundTimer) {
            clearInterval(soundTimer);
            soundTimer = null;
        } else {
            startSound();
        }
    });

    form?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const message = form.message.value.trim();
        if (!message) return;
        const response = await fetch("/support/messages", {
            method: "POST",
            headers: { "Content-Type": "application/json", "Accept": "application/json" },
            body: JSON.stringify({
                message,
                guest_name: form.guest_name?.value.trim() || "",
                guest_email: form.guest_email?.value.trim() || "",
            }),
        });
        const data = await response.json();
        statusNode.textContent = data.message || data.error || "";
        if (data.ok) {
            form.message.value = "";
            await loadMessages();
        }
    });

    if (supportWidget.classList.contains("support-center-panel")) {
        loadMessages();
    }
});

document.querySelectorAll("[data-open-client-support]").forEach((button) => {
    button.addEventListener("click", () => {
        const widget = document.querySelector("[data-rich-support]");
        const toggle = widget?.querySelector("[data-support-toggle]");
        if (!widget || !toggle) return;
        if (!widget.classList.contains("open")) {
            toggle.click();
        } else {
            widget.querySelector("[data-support-thread]")?.scrollTo({ top: 99999, behavior: "smooth" });
        }
    });
});

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

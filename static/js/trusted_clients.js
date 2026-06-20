document.addEventListener("DOMContentLoaded", () => {
  const tooltip = document.getElementById("trusted-tooltip");
  const points = document.querySelectorAll(".trusted-point");
  const activityList = document.getElementById("trusted-activity-list");
  const clock = document.getElementById("trusted-map-clock");
  const investorsCounter = document.getElementById("trusted-investors-counter");
  const operationsCounter = document.getElementById("trusted-operations-counter");

  if (!tooltip || !activityList || !clock) return;

  const activities = [
    { initials: "NY", name: "Demo U.", country: "United States", activity: "اتصال منصة", status: "مكتمل" },
    { initials: "LD", name: "Demo K.", country: "United Kingdom", activity: "طلب ربط", status: "قيد المراجعة" },
    { initials: "DB", name: "Demo E.", country: "UAE", activity: "تحديث محفظة", status: "مكتمل" },
    { initials: "RY", name: "Demo S.", country: "Saudi Arabia", activity: "تفعيل بطاقة", status: "مكتمل" },
    { initials: "SG", name: "Demo G.", country: "Singapore", activity: "تحديث حساب", status: "مكتمل" },
    { initials: "TK", name: "Demo J.", country: "Japan", activity: "إنشاء تذكرة", status: "مكتمل" },
    { initials: "FR", name: "Demo F.", country: "France", activity: "طلب دعم", status: "قيد المراجعة" },
    { initials: "DZ", name: "Demo A.", country: "Algeria", activity: "متابعة بطاقة", status: "مكتمل" }
  ];
  let operationsTotal = 842190;

  function statusClass(status) {
    if (status === "مكتمل") return "done";
    if (status === "مرفوض") return "rejected";
    return "pending";
  }

  function renderActivities() {
    const shuffled = [...activities].sort(() => Math.random() - 0.5).slice(0, 5);

    activityList.innerHTML = shuffled.map(item => `
      <div class="trusted-activity-item">
        <div class="trusted-avatar">${item.initials}</div>
        <div class="trusted-activity-meta">
          <strong>${item.name}</strong>
          <small>${item.country} — ${item.activity}</small>
        </div>
        <span class="trusted-status ${statusClass(item.status)}">${item.status}</span>
      </div>
    `).join("");
  }

  function updateClock() {
    const now = new Date();
    clock.textContent = now.toLocaleTimeString("ar-DZ", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });
  }

  function updateCounters() {
    if (investorsCounter) {
      const investors = 18000 + Math.floor(Math.random() * 7001);
      investorsCounter.textContent = investors.toLocaleString("en-US");
    }
    if (operationsCounter) {
      operationsTotal += 3 + Math.floor(Math.random() * 14);
      operationsCounter.textContent = operationsTotal.toLocaleString("en-US");
    }
  }

  points.forEach(point => {
    point.addEventListener("mousemove", (event) => {
      const canvas = point.closest(".trusted-map-canvas");
      const rect = canvas.getBoundingClientRect();
      const country = point.dataset.country;
      const activity = point.dataset.activity;

      tooltip.style.display = "block";
      tooltip.style.left = `${event.clientX - rect.left + 18}px`;
      tooltip.style.top = `${event.clientY - rect.top + 18}px`;
      tooltip.innerHTML = `
        <strong>${country}</strong><br>
        <span>${activity}</span><br>
        <small>نشاط مباشر تجريبي</small>
      `;
    });

    point.addEventListener("mouseleave", () => {
      tooltip.style.display = "none";
    });
  });

  renderActivities();
  updateClock();
  updateCounters();

  setInterval(renderActivities, 5000);
  setInterval(updateClock, 1000);
  setInterval(updateCounters, 2600);
});

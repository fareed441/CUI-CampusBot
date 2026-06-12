function getClassCode() {
  return document.getElementById("class-code").value.trim().toUpperCase();
}

function viewTimetable() {
  const code = getClassCode();
  if (!code) {
    alert("Enter class code");
    return;
  }

  document.getElementById(
    "pdf-viewer"
  ).src = `/api/timetable/class/${encodeURIComponent(code)}/pdf`;
}

function downloadTimetable() {
  const code = getClassCode();
  if (!code) {
    alert("Enter class code");
    return;
  }

  window.open(
    `/api/timetable/class/${encodeURIComponent(code)}/download`,
    "_blank"
  );
}

function downloadFullTimetable() {
  window.open("/api/timetable/download-full", "_blank");
}

function categoryLabel(value) {
  const labels = {
    fee: "Fee Notification",
    semester_calendar: "Semester Calendar",
    mid_datesheet: "Midterm Datesheet",
    final_datesheet: "Final Datesheet",
    general: "General Notice",
  };
  return labels[value] || value || "Notice";
}

async function loadNotifications() {
  const container = document.getElementById("notifications-container");

  try {
    const response = await fetch("/api/notifications");
    if (!response.ok) {
      container.innerHTML =
        '<p class="text-red-300">Failed to load notifications.</p>';
      return;
    }

    const data = await response.json();
    container.innerHTML = "";

    if (!Array.isArray(data) || data.length === 0) {
      container.innerHTML = '<p class="text-gray-400">No notices uploaded yet.</p>';
      return;
    }

    data.forEach((item) => {
      container.innerHTML += `
        <div class="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <h3 class="text-lg font-semibold text-white mb-2">${item.title}</h3>
          <p class="text-sm text-cyan-400 mb-4">${categoryLabel(item.category)}</p>
          <div class="flex gap-3">
            <button
              onclick="window.open('/api/notifications/${item.id}/view', '_blank')"
              class="px-4 py-2 bg-cyan-600 rounded-lg hover:bg-cyan-700"
            >
              View
            </button>

            <button
              onclick="window.open('/api/notifications/${item.id}/download', '_blank')"
              class="px-4 py-2 bg-green-600 rounded-lg hover:bg-green-700"
            >
              Download
            </button>
          </div>
        </div>
      `;
    });
  } catch (error) {
    container.innerHTML =
      '<p class="text-red-300">Server error while loading notifications.</p>';
  }
}

loadNotifications();


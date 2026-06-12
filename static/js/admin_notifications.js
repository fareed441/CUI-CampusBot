function setAdminMessage(message, isError = false) {
  const el = document.getElementById("admin-message");
  el.textContent = message;
  el.className = isError
    ? "mt-4 text-sm text-red-300"
    : "mt-4 text-sm text-cyan-200";
}

async function uploadTimetable() {
  const fileInput = document.getElementById("timetable-file");
  const file = fileInput.files[0];

  if (!file) {
    setAdminMessage("Select a timetable PDF first.", true);
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch("/api/admin/upload-timetable", {
      method: "POST",
      body: formData,
    });

    const data = await response.json();
    if (!response.ok) {
      setAdminMessage(data.error || "Failed to upload timetable.", true);
      return;
    }

    setAdminMessage(`Timetable uploaded. Classes detected: ${data.total_classes}`);
    fileInput.value = "";
  } catch (error) {
    setAdminMessage("Server error while uploading timetable.", true);
  }
}

async function uploadNotification() {
  const title = document.getElementById("notification-title").value.trim();
  const category = document.getElementById("notification-category").value;
  const fileInput = document.getElementById("notification-file");
  const file = fileInput.files[0];

  if (!title) {
    setAdminMessage("Notification title is required.", true);
    return;
  }
  if (!file) {
    setAdminMessage("Select a notification file.", true);
    return;
  }

  const formData = new FormData();
  formData.append("title", title);
  formData.append("category", category);
  formData.append("file", file);

  try {
    const response = await fetch("/api/admin/upload-notification", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();

    if (!response.ok) {
      setAdminMessage(data.error || "Failed to upload notification.", true);
      return;
    }

    setAdminMessage("Notification uploaded successfully.");
    document.getElementById("notification-title").value = "";
    document.getElementById("notification-file").value = "";
  } catch (error) {
    setAdminMessage("Server error while uploading notification.", true);
  }
}


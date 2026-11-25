import { useEffect, useState } from "react";
import API from "../../api";

export default function LectureTeacher({
  teachingId,
}) {

  // ================= STATES =================
  const [lectures, setLectures] =
    useState([]);

  const [showForm, setShowForm] =
    useState(false);

  const [editingId, setEditingId] =
    useState(null);

  const [uploading, setUploading] =
    useState(false);

  // ================= FORM =================
  const [form, setForm] =
    useState({

      title: "",

      description: "",

      chapter: "",

      video: null,

      notes: null,

      meeting_link: "",

      // LIVE CLASS
      is_live: false,

      scheduled_time: "",
    });

  // ================= FETCH LECTURES =================
  const fetchLectures = async () => {

    try {

      const res = await API.get(
        `/lectures/?teaching_assignment=${teachingId}`
      );

      setLectures(
        res.data?.results ||
        res.data ||
        []
      );

    } catch (err) {

      console.log(
        "Lecture fetch error:",
        err
      );
    }
  };

  useEffect(() => {

    if (teachingId) {

      fetchLectures();
    }

  }, [teachingId]);

  // ================= HANDLE INPUT =================
  const handleChange = (e) => {

    const {
      name,
      value,
      type,
      checked
    } = e.target;

    setForm({

      ...form,

      [name]:
        type === "checkbox"
          ? checked
          : value,
    });
  };

  // ================= VIDEO =================
  const handleVideoChange = (e) => {

    setForm({

      ...form,

      video:
        e.target.files[0],
    });
  };

  // ================= NOTES =================
  const handleNotesChange = (e) => {

    setForm({

      ...form,

      notes:
        e.target.files[0],
    });
  };

  // ================= RESET FORM =================
  const resetForm = () => {

    setForm({

      title: "",

      description: "",

      chapter: "",

      video: null,

      notes: null,

      meeting_link: "",

      is_live: false,

      scheduled_time: "",
    });

    setEditingId(null);

    setShowForm(false);
  };

  // ================= CREATE / UPDATE =================
  const handleUpload = async () => {

    if (!form.title.trim()) {

      return alert(
        "Lecture title is required"
      );
    }

    try {

      setUploading(true);

      const fd = new FormData();

      fd.append(
        "title",
        form.title
      );

      fd.append(
        "description",
        form.description
      );

      fd.append(
        "chapter",
        form.chapter
      );

      fd.append(
        "teaching_assignment",
        teachingId
      );

      // ================= LIVE CLASS =================
      fd.append(
        "is_live",
        form.is_live
      );

      if (
        form.scheduled_time
      ) {

        fd.append(
          "scheduled_time",
          form.scheduled_time
        );
      }

      // ================= VIDEO =================
      if (form.video) {

        fd.append(
          "video",
          form.video
        );
      }

      // ================= NOTES =================
      if (form.notes) {

        fd.append(
          "notes",
          form.notes
        );
      }

      // ================= LINK =================
      if (form.meeting_link) {

        fd.append(
          "meeting_link",
          form.meeting_link
        );
      }

      // ================= UPDATE =================
      if (editingId) {

        await API.patch(
          `/lectures/${editingId}/`,
          fd,
          {
            headers: {
              "Content-Type":
                "multipart/form-data",
            },
          }
        );

        alert(
          "Lecture updated successfully"
        );
      }

      // ================= CREATE =================
      else {

        await API.post(
          "/lectures/",
          fd,
          {
            headers: {
              "Content-Type":
                "multipart/form-data",
            },
          }
        );

        alert(
          "Lecture uploaded successfully"
        );
      }

      resetForm();

      fetchLectures();

    } catch (err) {

      console.log(
        err.response?.data || err
      );

      alert(
        "Operation failed"
      );

    } finally {

      setUploading(false);
    }
  };

  // ================= EDIT =================
  const editLecture = (lecture) => {

    setShowForm(true);

    setEditingId(lecture.id);

    setForm({

      title:
        lecture.title || "",

      description:
        lecture.description || "",

      chapter:
        lecture.chapter || "",

      meeting_link:
        lecture.meeting_link || "",

      is_live:
        lecture.is_live || false,

      scheduled_time:
        lecture.scheduled_time
          ? lecture.scheduled_time.slice(
              0,
              16
            )
          : "",

      video: null,

      notes: null,
    });
  };

  // ================= DELETE =================
  const deleteLecture = async (id) => {

    const confirmDelete =
      window.confirm(
        "Delete this lecture?"
      );

    if (!confirmDelete) return;

    try {

      await API.delete(
        `/lectures/${id}/`
      );

      alert(
        "Lecture deleted"
      );

      fetchLectures();

    } catch (err) {

      console.log(err);

      alert(
        "Delete failed"
      );
    }
  };

  return (
    <div className="card">

      {/* ================= HEADER ================= */}
      <div
        style={{
          display: "flex",
          justifyContent:
            "space-between",
          alignItems: "center",
          marginBottom: "20px",
        }}
      >

        <h3>
          Lectures
        </h3>

        <button
          className="btn-primary"
          onClick={() =>
            setShowForm(!showForm)
          }
        >

          {showForm
            ? "Cancel"
            : "+ Add Lecture"}

        </button>

      </div>

      {/* ================= FORM ================= */}
      {showForm && (

        <div
          style={{
            marginBottom: "25px",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >

          {/* TITLE */}
          <input
            type="text"
            name="title"
            placeholder="Lecture Title"
            value={form.title}
            onChange={handleChange}
          />

          {/* CHAPTER */}
          <input
            type="text"
            name="chapter"
            placeholder="Chapter"
            value={form.chapter}
            onChange={handleChange}
          />

          {/* DESCRIPTION */}
          <textarea
            name="description"
            placeholder="Description"
            rows="4"
            value={form.description}
            onChange={handleChange}
          />

          {/* ================= LIVE CLASS ================= */}
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
            }}
          >

            <input
              type="checkbox"
              name="is_live"
              checked={
                form.is_live
              }
              onChange={
                handleChange
              }
            />

            Live Class

          </label>

          {/* SCHEDULED TIME */}
          {form.is_live && (

            <input
              type="datetime-local"
              name="scheduled_time"
              value={
                form.scheduled_time
              }
              onChange={
                handleChange
              }
            />

          )}

          {/* VIDEO */}
          <input
            type="file"
            accept="video/*"
            onChange={
              handleVideoChange
            }
          />

          {/* NOTES */}
          <input
            type="file"
            accept=".pdf,.ppt,.pptx,.doc,.docx"
            onChange={
              handleNotesChange
            }
          />

          {/* LINK */}
          <input
            type="text"
            name="meeting_link"
            placeholder="YouTube / Meet / Zoom Link"
            value={
              form.meeting_link
            }
            onChange={
              handleChange
            }
          />

          {/* BUTTON */}
          <button
            className="btn-primary"
            onClick={
              handleUpload
            }
            disabled={
              uploading
            }
          >

            {uploading
              ? "Saving..."
              : editingId
              ? "Update Lecture"
              : "Upload Lecture"}

          </button>

        </div>

      )}

      {/* ================= TABLE ================= */}
      {lectures.length === 0 ? (

        <p>
          No lectures added
        </p>

      ) : (

        <div
          style={{
            overflowX: "auto",
          }}
        >

          <table>

            <thead>

              <tr>

                <th>
                  Title
                </th>

                <th>
                  Chapter
                </th>

                <th>
                  Type
                </th>

                <th>
                  Scheduled
                </th>

                <th>
                  Description
                </th>

                <th>
                  Actions
                </th>

              </tr>

            </thead>

            <tbody>

              {lectures.map(
                (lecture) => (

                  <tr
                    key={lecture.id}
                  >

                    {/* TITLE */}
                    <td>
                      {
                        lecture.title
                      }
                    </td>

                    {/* CHAPTER */}
                    <td>
                      {lecture.chapter ||
                        "-"}
                    </td>

                    {/* TYPE */}
                    <td>

                      {lecture.is_live ? (

                        <span
                          style={{
                            color:
                              "red",
                            fontWeight:
                              "bold",
                          }}
                        >
                          🔴 Live
                        </span>

                      ) : (

                        <span>
                          📹 Recorded
                        </span>

                      )}

                    </td>

                    {/* TIME */}
                    <td>

                      {lecture.scheduled_time

                        ? new Date(
                            lecture.scheduled_time
                          ).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: true })

                        : "-"}

                    </td>

                    {/* DESCRIPTION */}
                    <td>
                      {lecture.description ||
                        "-"}
                    </td>

                    {/* ACTIONS */}
                    <td>

                      <div
                        style={{
                          display:
                            "flex",
                          gap: "8px",
                          flexWrap:
                            "wrap",
                        }}
                      >

                        {/* VIDEO */}
                        {lecture.video && (

                          <a
                            href={
                              lecture.video
                            }
                            target="_blank"
                            rel="noreferrer"
                          >

                            <button>
                              Video
                            </button>

                          </a>

                        )}

                        {/* NOTES */}
                        {lecture.notes && (

                          <a
                            href={
                              lecture.notes
                            }
                            target="_blank"
                            rel="noreferrer"
                          >

                            <button>
                              Notes
                            </button>

                          </a>

                        )}

                        {/* LINK */}
                        {lecture.meeting_link && (

                          <a
                            href={
                              lecture.meeting_link
                            }
                            target="_blank"
                            rel="noreferrer"
                          >

                            <button
                              style={{
                                background:
                                  lecture.is_live
                                    ? "red"
                                    : "",
                                color:
                                  lecture.is_live
                                    ? "white"
                                    : "",
                              }}
                            >

                              {lecture.is_live
                                ? "Join Live"
                                : "Open Link"}

                            </button>

                          </a>

                        )}

                        {/* EDIT */}
                        <button
                          className="btn-primary"
                          onClick={() =>
                            editLecture(
                              lecture
                            )
                          }
                        >
                          Edit
                        </button>

                        {/* DELETE */}
                        <button
                          onClick={() =>
                            deleteLecture(
                              lecture.id
                            )
                          }
                          style={{
                            background:
                              "red",
                            color:
                              "white",
                            border:
                              "none",
                            padding:
                              "8px 12px",
                            borderRadius:
                              "6px",
                            cursor:
                              "pointer",
                          }}
                        >
                          Delete
                        </button>

                      </div>

                    </td>

                  </tr>

                )
              )}

            </tbody>

          </table>

        </div>

      )}

    </div>
  );
}
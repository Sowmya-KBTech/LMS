import { useEffect, useState } from "react";
import API from "../../api";

export default function LectureStudent({
  teachingId,
}) {

  // ================= STATES =================
  const [lectures, setLectures] =
    useState([]);

  const [loading, setLoading] =
    useState(true);

  // ✅ SEARCH
  const [search, setSearch] =
    useState("");

  // ✅ FILTER
  const [filterType, setFilterType] =
    useState("all");

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

    } finally {

      setLoading(false);
    }
  };

  // ================= LOAD =================
  useEffect(() => {

    if (teachingId) {

      fetchLectures();
    }

  }, [teachingId]);

  // ================= FILTERED LECTURES =================
  const filteredLectures =
    lectures.filter((lecture) => {

      // SEARCH
      const matchesSearch =

        lecture.title
          ?.toLowerCase()
          .includes(
            search.toLowerCase()
          )

        ||

        lecture.chapter
          ?.toLowerCase()
          .includes(
            search.toLowerCase()
          );

      // FILTER
      const matchesType =

        filterType === "all"

        ||

        (
          filterType === "live"
          &&
          lecture.is_live
        )

        ||

        (
          filterType === "recorded"
          &&
          !lecture.is_live
        );

      return (
        matchesSearch
        &&
        matchesType
      );
    });

  return (
    <div className="card">

      {/* ================= HEADER ================= */}
      <div
        style={{
          marginBottom: "20px",
        }}
      >

        <h2>
          Lectures
        </h2>

        <p>
          View lecture videos and live classes
        </p>

      </div>

      {/* ================= SEARCH + FILTER ================= */}
      <div
        style={{
          display: "flex",
          gap: "12px",
          marginBottom: "20px",
          flexWrap: "wrap",
        }}
      >

        {/* SEARCH */}
        <input
          type="text"
          placeholder="Search lecture..."
          value={search}
          onChange={(e) =>
            setSearch(
              e.target.value
            )
          }
          style={{
            flex: 1,
            minWidth: "220px",
          }}
        />

        {/* FILTER */}
        <select
          value={filterType}
          onChange={(e) =>
            setFilterType(
              e.target.value
            )
          }
        >

          <option value="all">
            All Lectures
          </option>

          <option value="live">
            Live Classes
          </option>

          <option value="recorded">
            Recorded
          </option>

        </select>

      </div>

      {/* ================= LOADING ================= */}
      {loading ? (

        <p>
          Loading lectures...
        </p>

      ) : filteredLectures.length === 0 ? (

        <p>
          No lectures found
        </p>

      ) : (

        <div
          style={{
            overflowX: "auto",
          }}
        >

          <table>

            {/* ================= HEADER ================= */}
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
                  Action
                </th>

              </tr>

            </thead>

            {/* ================= BODY ================= */}
            <tbody>

              {filteredLectures.map(
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

                    {/* SCHEDULE */}
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

                    {/* ACTION */}
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

                            <button
                              className="btn-primary"
                            >
                              Open Video
                            </button>

                          </a>

                        )}

                        {/* LIVE / LINK */}
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

                        {/* EMPTY */}
                        {!lecture.video &&
                          !lecture.meeting_link && (

                          <span>
                            No lecture file
                          </span>

                        )}

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
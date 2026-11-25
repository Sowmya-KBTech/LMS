import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

export default function CourseStructure() {

  const { id } = useParams();

  const navigate = useNavigate();

  const [open, setOpen] =
    useState(false);

  const [course, setCourse] =
    useState(null);

  const [years, setYears] =
    useState([]);

  const [loading, setLoading] =
    useState(true);

  // ================= INIT =================
  useEffect(() => {

    if (id) {

      init();
    }

  }, [id]);

  // ================= LOAD DATA =================
  const init = async () => {

    try {

      setLoading(true);

      // ================= COURSE =================
      const c = await API.get(
        `/courses/${id}/`
      );

      setCourse(c.data);

      // ================= YEARS (subjects nested) =================
      const y = await API.get(
        `/years/?course=${id}`
      );

      setYears(
        y.data?.results ||
        y.data ||
        []
      );

    } catch (err) {

      console.error(
        "Course structure error:",
        err
      );

    } finally {

      setLoading(false);
    }
  };

  // ================= CREDITS HELPER =================
  const creditsOf = (s) =>
    Number(s.credits) || 0;

  // ================= FLATTEN SUBJECTS =================
  const allSubjects =
    years.flatMap(
      (y) => y.subjects || []
    );

  // ================= UNIQUE SORTED SEMESTERS =================
  const semesters = [
    ...new Set(
      allSubjects.map(
        (s) => Number(s.semester)
      )
    ),
  ]
    .filter(
      (n) => !Number.isNaN(n)
    )
    .sort((a, b) => a - b);

  // ================= GRAND TOTAL =================
  const grandTotal =
    allSubjects.reduce(
      (sum, s) =>
        sum + creditsOf(s),
      0
    );

  // ================= LOADING =================
  if (loading) {

    return (
      <p style={{ padding: "20px" }}>
        Loading...
      </p>
    );
  }

  // ================= NO DATA =================
  if (!course) {

    return (
      <p style={{ padding: "20px" }}>
        Course not found
      </p>
    );
  }

  return (
    <div className="app">

      {/* NAVBAR */}
      <Navbar setOpen={setOpen} />

      <div className="layout">

        {/* SIDEBAR */}
        <Sidebar
          open={open}
          setOpen={setOpen}
        />

        {/* MAIN */}
        <div className="main">

          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">

              <button
                className="btn-primary"
                onClick={() =>
                  navigate(-1)
                }
              >
                ← Back
              </button>

              <h2>
                {course.name} — Course Structure
              </h2>

              <p>
                Subjects grouped by semester with credit totals
              </p>

            </div>

            {/* ================= EMPTY ================= */}
            {allSubjects.length === 0 ? (

              <div className="card">

                <p>
                  No subjects added yet
                </p>

              </div>

            ) : (

              <>

                {/* ================= PER SEMESTER ================= */}
                {semesters.map((sem) => {

                  const list =
                    allSubjects
                      .filter(
                        (s) =>
                          Number(
                            s.semester
                          ) === sem
                      )
                      .sort((a, b) =>
                        (a.code || "").localeCompare(
                          b.code || ""
                        )
                      );

                  const subtotal =
                    list.reduce(
                      (sum, s) =>
                        sum + creditsOf(s),
                      0
                    );

                  return (

                    <div
                      className="card"
                      key={sem}
                    >

                      <h3>
                        Semester {sem}
                      </h3>

                      <table>

                        <thead>

                          <tr>

                            <th>
                              Code
                            </th>

                            <th>
                              Subject
                            </th>

                            <th>
                              Credits
                            </th>

                          </tr>

                        </thead>

                        <tbody>

                          {list.map((s) => (

                            <tr key={s.id}>

                              <td>
                                {s.code || "—"}
                              </td>

                              <td>
                                {s.name}
                              </td>

                              <td>
                                {creditsOf(s)}
                              </td>

                            </tr>

                          ))}

                          {/* SUBTOTAL */}
                          <tr>

                            <td
                              colSpan="2"
                              style={{
                                textAlign:
                                  "right",
                                fontWeight:
                                  "bold",
                              }}
                            >
                              Semester {sem} Total
                            </td>

                            <td
                              style={{
                                fontWeight:
                                  "bold",
                              }}
                            >
                              {subtotal}
                            </td>

                          </tr>

                        </tbody>

                      </table>

                    </div>

                  );
                })}

                {/* ================= GRAND TOTAL ================= */}
                <div className="card">

                  <h3>
                    Grand Total Credits: {grandTotal}
                  </h3>

                </div>

              </>

            )}

          </div>

        </div>

      </div>

    </div>
  );
}
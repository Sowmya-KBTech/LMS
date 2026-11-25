import { useState, useEffect, useRef } from "react";
import API from "../../api";

export default function DiscussionTeacher({
  teachingId,
}) {

  const [message, setMessage] =
    useState("");

  const [messages, setMessages] =
    useState([]);

  const [loading, setLoading] =
    useState(true);

  const chatEndRef = useRef(null);

  const currentUser =
    JSON.parse(
      localStorage.getItem("user")
    );

  useEffect(() => {

    if (!teachingId) return;

    loadMessages();

    const interval = setInterval(
      loadMessages,
      3000
    );

    return () =>
      clearInterval(interval);

  }, [teachingId]);

  useEffect(() => {

    chatEndRef.current?.scrollIntoView({
      behavior: "smooth",
    });

  }, [messages]);

  const loadMessages = async () => {

    try {

      const res = await API.get(
        `/discussions/?teaching_assignment=${teachingId}`
      );

      setMessages(
        res.data?.results ||
        res.data ||
        []
      );

    } catch (err) {

      console.error(
        "LOAD ERROR:",
        err.response?.data || err
      );

    } finally {

      setLoading(false);
    }
  };

  const sendMessage = async () => {

    if (!message.trim()) {
      return;
    }

    try {

      await API.post(
        "/discussions/",
        {
          teaching_assignment:
            teachingId,
          message,
        }
      );

      setMessage("");

      loadMessages();

    } catch (err) {

      console.log(
        "BACKEND ERROR:",
        err.response?.data
      );

      console.error(err);
    }
  };

  return (

    <div
      style={{
        background: "#fff",
        borderRadius: "16px",
        overflow: "hidden",
        height: "70vh",
        display: "flex",
        flexDirection: "column",
      }}
    >

      {/* HEADER */}
      <div
        style={{
          padding: "18px 25px",
          borderBottom:
            "1px solid #eee",
          fontWeight: "300",
          fontSize: "15px"
        }}
      >
        Discussion Forum
      </div>

      {/* CHAT AREA */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "20px",
          background: "#f4f5f7",
        }}
      >

        {loading ? (

          <p>Loading...</p>

        ) : messages.length === 0 ? (

          <div
            style={{
              textAlign: "center",
              color: "#777",
              marginTop: "100px",
            }}
          >
            No messages yet
          </div>

        ) : (

          messages.map((msg) => {

            const isCurrentUser =
              currentUser &&
              msg.user_name ===
              currentUser.username;

            return (

              <div
                key={msg.id}
                style={{
                  display: "flex",
                  justifyContent:
                    isCurrentUser
                      ? "flex-end"
                      : "flex-start",
                  marginBottom: "15px",
                }}
              >

                <div
                  style={{
                    maxWidth: "70%",
                    background:
                      isCurrentUser
                        ? "#d9fdd3"
                        : "#ffffff",
                    padding: "12px 15px",
                    borderRadius: "14px",
                    boxShadow:
                      "0 1px 3px rgba(0,0,0,0.1)",
                  }}
                >

                  <div
                    style={{
                      fontWeight: "600",
                      marginBottom: "6px",
                    }}
                  >
                    {msg.user_name}
                  </div>

                  <div>
                    {msg.message}
                  </div>

                  <div
                    style={{
                      fontSize: "12px",
                      color: "#777",
                      textAlign: "right",
                      marginTop: "6px",
                    }}
                  >
                    {new Date(
                      msg.created_at
                    ).toLocaleString()}
                  </div>

                </div>

              </div>
            );
          })

        )}

        <div ref={chatEndRef} />

      </div>

      {/* MESSAGE BOX */}
      <div
        style={{
          display: "flex",
          gap: "10px",
          padding: "15px",
          borderTop:
            "1px solid #eee",
          background: "#fff",
        }}
      >

        <input
          type="text"
          value={message}
          onChange={(e) =>
            setMessage(
              e.target.value
            )
          }
          placeholder="Type a message..."
          style={{
            flex: 1,
            padding: "14px",
            borderRadius: "25px",
            border:
              "1px solid #ddd",
            outline: "none",
          }}
          onKeyDown={(e) => {

            if (e.key === "Enter") {

              sendMessage();

            }

          }}
        />

        <button
          onClick={sendMessage}
          style={{
            background: "#6d25d3",
            color: "#fff",
            border: "none",
            borderRadius: "25px",
            padding:
              "12px 25px",
            cursor: "pointer",
            fontWeight: "600",
          }}
        >
          Send
        </button>

      </div>

    </div>
  );
}
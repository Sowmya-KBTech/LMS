import API from "../api";

const CHECKOUT_SRC = "https://checkout.razorpay.com/v1/checkout.js";

/**
 * Load Razorpay's checkout script once and reuse it.
 * Re-injecting the tag on every payment leaks listeners and slows the popup.
 */
function loadCheckout() {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) return resolve();

    const existing = document.querySelector(`script[src="${CHECKOUT_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("load failed")));
      return;
    }

    const s = document.createElement("script");
    s.src = CHECKOUT_SRC;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Could not reach Razorpay."));
    document.body.appendChild(s);
  });
}

/**
 * Run one online payment against a Fee.
 *
 * The amount is a SUGGESTION. The server derives what is actually owed from
 * the fee's payment rows and will reject anything above it - the same rule
 * the offline pay endpoint follows.
 *
 * Resolves when the server has verified the payment. Rejects with a message
 * safe to show the user. A closed popup rejects with code "dismissed" so the
 * caller can stay quiet rather than showing a scary error.
 */
export async function payFeeOnline({ feeId, amount }) {
  await loadCheckout();

  // Step 1: server opens the order (in THIS college's Razorpay account) and
  // tells us what to charge. Show the server's reason if it refuses - for
  // example "Online payment isn't set up for this college yet."
  let order;
  try {
    ({ data: order } = await API.post(`/fees/${feeId}/initiate-payment/`, {
      amount,
    }));
  } catch (err) {
    throw new Error(err.response?.data?.detail || "Could not start the payment. Try again.");
  }

  return new Promise((resolve, reject) => {
    const rzp = new window.Razorpay({
      key: order.key_id,          // public key - the secret never comes here
      amount: order.amount_paise,
      currency: order.currency,
      order_id: order.order_id,
      name: "College Fee Payment",
      description: order.fee_term,
      prefill: { name: order.student_name },
      theme: { color: "#0f172a" },

      // Step 2: checkout finished. Nothing is recorded yet - the browser is
      // not trusted. The server checks the signature before believing this.
      handler: async (res) => {
        try {
          const { data } = await API.post("/payments/verify/", {
            razorpay_order_id: res.razorpay_order_id,
            razorpay_payment_id: res.razorpay_payment_id,
            razorpay_signature: res.razorpay_signature,
          });
          resolve(data);
        } catch (err) {
          reject(
            new Error(
              err.response?.data?.detail ||
                "Payment went through but could not be confirmed. " +
                  "Refresh in a minute before trying again."
            )
          );
        }
      },

      modal: {
        ondismiss: () => {
          const e = new Error("Payment cancelled.");
          e.code = "dismissed";
          reject(e);
        },
      },
    });

    // A failed card or expired UPI request - the popup stays open, so just
    // surface the reason.
    rzp.on("payment.failed", (res) => {
      reject(new Error(res.error?.description || "Payment failed."));
    });

    rzp.open();
  });
}
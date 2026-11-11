"use strict";

(() => {
  const assistantIcon = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3.5a7.5 7.5 0 0 0-7.5 7.5v3.2A2.8 2.8 0 0 0 7.3 17H8v-6H7.3c-.7 0-1.3.2-1.8.6m10.5 5.3h.7a2.8 2.8 0 0 0 2.8-2.8V11a7.5 7.5 0 0 0-15 0" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M9.5 19h3.2a2 2 0 0 0 2-2v-.3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';
  const citationIcon = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M8.5 12.5 11 15a3.5 3.5 0 0 0 5 0l3-3a3.5 3.5 0 0 0-5-5l-1.2 1.2M15.5 11.5 13 9a3.5 3.5 0 0 0-5 0l-3 3a3.5 3.5 0 0 0 5 5l1.2-1.2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  function initialize({
    document: doc = window.document,
    fetchImpl = window.fetch ? window.fetch.bind(window) : null,
    apiBaseUrl = window.PEOPLEDESK_CONFIG?.apiBaseUrl || "",
  } = {}) {
    const chatBody = doc.getElementById("chatBody");
    const input = doc.getElementById("questionInput");
    const form = doc.getElementById("chatForm");
    const sendButton = doc.getElementById("sendButton");
    const resetButton = doc.getElementById("resetButton");
    const suggestionButtons = Array.from(doc.querySelectorAll(".suggestion"));
    const actionButtons = [sendButton, resetButton, ...suggestionButtons].filter(Boolean);

    function scrollToLatest() {
      chatBody.scrollTop = chatBody.scrollHeight;
    }

    function addMessage(text, kind, citations = [], { loading = false } = {}) {
      const row = doc.createElement("div");
      row.className = `message-row ${kind}`;
      if (loading) row.dataset.loading = "true";

      if (kind === "assistant") {
        const avatar = doc.createElement("span");
        avatar.className = "mini-avatar";
        avatar.setAttribute("aria-hidden", "true");
        avatar.innerHTML = assistantIcon;
        row.appendChild(avatar);
      }

      const bubble = doc.createElement("div");
      bubble.className = loading ? "bubble loading-bubble" : "bubble";
      bubble.textContent = text;

      if (Array.isArray(citations) && citations.length > 0) {
        const citationBox = doc.createElement("div");
        citationBox.className = "citation-list";
        citationBox.setAttribute("aria-label", "Policy sources");

        citations.forEach((citation) => {
          if (!citation || typeof citation !== "object") return;
          const citationItem = doc.createElement("div");
          citationItem.className = "citation";
          citationItem.innerHTML = citationIcon;

          const details = doc.createElement("div");
          details.className = "citation-details";
          const source = doc.createElement("strong");
          source.textContent = citation.document || citation.document_id || "Source document unavailable";
          details.appendChild(source);

          const parts = [citation.section, citation.chunk_id ? `Chunk ${citation.chunk_id}` : ""];
          if (citation.page_number !== null && citation.page_number !== undefined) {
            parts.push(`Page ${citation.page_number}`);
          }
          const metadata = doc.createElement("span");
          metadata.className = "citation-meta";
          metadata.textContent = parts.filter(Boolean).join(" · ");
          if (metadata.textContent) details.appendChild(metadata);

          if (typeof citation.quote === "string" && citation.quote) {
            const quote = doc.createElement("blockquote");
            quote.className = "citation-quote";
            quote.textContent = `“${citation.quote}”`;
            details.appendChild(quote);
          }

          citationItem.appendChild(details);
          citationBox.appendChild(citationItem);
        });
        if (citationBox.children.length > 0) bubble.appendChild(citationBox);
      }

      row.appendChild(bubble);
      chatBody.appendChild(row);
      scrollToLatest();
      return row;
    }

    function setBusy(busy) {
      actionButtons.forEach((button) => { button.disabled = busy; });
      input.disabled = busy;
      form.setAttribute("aria-busy", String(busy));
    }

    function errorAnswer(response, payload) {
      if (payload && typeof payload.answer === "string") return payload.answer;
      const detail = payload && payload.detail;
      if (detail && typeof detail === "object" && typeof detail.answer === "string") {
        return detail.answer;
      }
      if (response.status === 422) {
        return "Please enter a valid HR policy question using 1 to 2000 characters.";
      }
      if (detail && typeof detail === "string") return detail;
      return "The policy service could not process your question. Please try again later.";
    }

    async function sendQuestion(rawQuestion) {
      const question = typeof rawQuestion === "string" ? rawQuestion.trim() : "";
      if (!question) {
        addMessage("Please enter a question about an HR policy.", "assistant");
        return;
      }

      addMessage(question, "user");
      const normalizedBaseUrl = typeof apiBaseUrl === "string" ? apiBaseUrl.trim().replace(/\/+$/, "") : "";
      if (!normalizedBaseUrl) {
        addMessage("The backend URL is not configured. Set PEOPLEDESK_API_BASE_URL and run python frontend/build_config.py before starting the frontend.", "assistant");
        return;
      }
      if (typeof fetchImpl !== "function") {
        addMessage("This browser does not provide the fetch API required to contact the policy service.", "assistant");
        return;
      }

      setBusy(true);
      const loadingRow = addMessage("Searching the available HR policies…", "assistant", [], { loading: true });
      try {
        const response = await fetchImpl(`${normalizedBaseUrl}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
        });
        let payload;
        try {
          payload = await response.json();
        } catch (_error) {
          payload = null;
        }

        loadingRow.remove();
        if (!response.ok) {
          addMessage(errorAnswer(response, payload), "assistant");
          return;
        }
        if (!payload || typeof payload.answer !== "string" || !Array.isArray(payload.citations)) {
          addMessage("The policy service returned an unexpected response. Please try again later.", "assistant");
          return;
        }
        addMessage(payload.answer, "assistant", payload.citations);
      } catch (_error) {
        loadingRow.remove();
        addMessage("I couldn't reach the policy service. Check that the backend is running and the API URL is correct, then try again.", "assistant");
      } finally {
        if (loadingRow.parentNode) loadingRow.remove();
        setBusy(false);
        input.focus();
      }
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const question = input.value;
      input.value = "";
      return sendQuestion(question);
    });

    suggestionButtons.forEach((button) => {
      button.addEventListener("click", () => sendQuestion(button.dataset.question));
    });

    resetButton.addEventListener("click", () => {
      chatBody.replaceChildren();
      const row = doc.createElement("div");
      row.className = "message-row";
      row.dataset.welcome = "true";
      const avatar = doc.createElement("span");
      avatar.className = "mini-avatar";
      avatar.setAttribute("aria-hidden", "true");
      avatar.innerHTML = assistantIcon;
      const bubble = doc.createElement("div");
      bubble.className = "bubble";
      bubble.textContent = "Hi! How can I help you with your HR policies today?";
      row.append(avatar, bubble);
      chatBody.appendChild(row);
      input.value = "";
      scrollToLatest();
      input.focus();
    });

    return { sendQuestion };
  }

  window.PeopleDeskChat = { initialize };
  initialize();
})();

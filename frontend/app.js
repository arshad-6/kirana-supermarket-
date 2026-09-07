// Kirana AI Manager Web Frontend Script
document.addEventListener("DOMContentLoaded", () => {
  const chatMessages = document.getElementById("chat-messages");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const btnSend = document.getElementById("btn-send");
  const btnNewChat = document.getElementById("btn-new-chat");
  const btnResetDemo = document.getElementById("btn-reset-demo");
  const scenarioChips = document.getElementById("scenario-chips");

  // Tab buttons
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");

  // Draft elements
  const draftItemsList = document.getElementById("draft-items-list");
  const draftSummary = document.getElementById("draft-summary");
  const draftSubtotal = document.getElementById("draft-subtotal");
  const draftCgst = document.getElementById("draft-cgst");
  const draftSgst = document.getElementById("draft-sgst");
  const draftGrandTotal = document.getElementById("draft-grand-total");
  const draftPaymentMode = document.getElementById("draft-payment-mode");
  const badgeDraftCount = document.getElementById("badge-draft-count");
  const btnQuickFinalize = document.getElementById("btn-quick-finalize");

  // Inventory elements
  const inventoryTbody = document.getElementById("inventory-tbody");
  const badgeStockCount = document.getElementById("badge-stock-count");
  const btnRefreshInv = document.getElementById("btn-refresh-inv");

  // Khata elements
  const khataCards = document.getElementById("khata-cards");
  const customerLedgerView = document.getElementById("customer-ledger-view");
  const ledgerCustomerTitle = document.getElementById("ledger-customer-title");
  const ledgerEntries = document.getElementById("ledger-entries");
  const btnCloseLedger = document.getElementById("btn-close-ledger");

  // Analytics elements
  const kpiSales = document.getElementById("kpi-sales");
  const kpiBills = document.getElementById("kpi-bills");
  const kpiGst = document.getElementById("kpi-gst");
  const kpiGstSplit = document.getElementById("kpi-gst-split");
  const splitUpi = document.getElementById("split-upi");
  const splitCash = document.getElementById("split-cash");
  const splitCard = document.getElementById("split-card");
  const btnRefreshAnalytics = document.getElementById("btn-refresh-analytics");
  const btnCloseDay = document.getElementById("btn-close-day");

  // Docs elements
  const btnGenPdf = document.getElementById("btn-gen-pdf");
  const btnGenPptx = document.getElementById("btn-gen-pptx");
  const fileLinks = document.getElementById("file-links");

  let sessionId = "web_session_" + Math.random().toString(36).substring(2, 9);
  const generatedDocsList = [];

  // Tab switching
  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      tabBtns.forEach(b => b.classList.remove("active"));
      tabPanes.forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const targetPane = document.getElementById(btn.dataset.tab);
      if (targetPane) targetPane.classList.add("active");
    });
  });

  // Scenario Chips click
  scenarioChips.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    const prompt = chip.getAttribute("data-prompt");
    if (prompt) {
      chatInput.value = prompt;
      sendMessage(prompt);
    }
  });

  // Chat submit
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const msg = chatInput.value.trim();
    if (!msg) return;
    sendMessage(msg);
  });

  // Action button triggers
  btnNewChat.addEventListener("click", () => sendMessage("/new"));
  btnQuickFinalize.addEventListener("click", () => sendMessage("Finalize"));
  btnGenPdf.addEventListener("click", () => sendMessage("Send me invoice as PDF"));
  btnGenPptx.addEventListener("click", () => sendMessage("Make this week's sales analysis deck"));
  btnRefreshInv.addEventListener("click", refreshInventory);
  btnRefreshAnalytics.addEventListener("click", refreshAnalytics);
  btnCloseDay.addEventListener("click", () => sendMessage("Close the day"));
  btnCloseLedger.addEventListener("click", () => {
    customerLedgerView.style.display = "none";
  });

  btnResetDemo.addEventListener("click", async () => {
    if (confirm("Reset store data back to initial seed state?")) {
      try {
        const res = await fetch("/api/reset-demo", { method: "POST" });
        const data = await res.json();
        appendMessage("assistant", "🔄 " + data.message);
        refreshAllPanels();
      } catch (err) {
        alert("Error resetting demo: " + err);
      }
    }
  });

  async function sendMessage(text) {
    appendMessage("user", text);
    chatInput.value = "";
    chatInput.focus();

    // Show typing indicator
    const typingElem = document.createElement("div");
    typingElem.className = "message assistant-message";
    typingElem.id = "typing-indicator";
    typingElem.innerHTML = `
      <div class="message-avatar">🤖</div>
      <div class="message-body">
        <div class="message-content"><em>Thinking & orchestrating domain tools...</em></div>
      </div>
    `;
    chatMessages.appendChild(typingElem);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId })
      });
      const data = await res.json();

      // Remove typing
      const typ = document.getElementById("typing-indicator");
      if (typ) typ.remove();

      appendAssistantResponse(data);
      refreshAllPanels();

      if (data.draft_bill) {
        renderDraftBill(data.draft_bill);
      }
    } catch (err) {
      const typ = document.getElementById("typing-indicator");
      if (typ) typ.remove();
      appendMessage("assistant", "⚠️ Server communication error: " + err.message);
    }
  }

  function appendMessage(role, text) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${role}-message`;
    const avatar = role === "user" ? "👤" : "🤖";
    const sender = role === "user" ? "Shop Owner" : "Kirana Manager AI";

    msgDiv.innerHTML = `
      <div class="message-avatar">${avatar}</div>
      <div class="message-body">
        <div class="message-sender">${sender}</div>
        <div class="message-content">${formatMarkdown(text)}</div>
      </div>
    `;
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function appendAssistantResponse(data) {
    const msgDiv = document.createElement("div");
    msgDiv.className = "message assistant-message";

    let toolTracesHtml = "";
    if (data.tool_traces && data.tool_traces.length > 0) {
      const toolsStr = data.tool_traces.map(t => t.tool || "tool").join(", ");
      toolTracesHtml = `
        <div class="tool-trace-badge" title='${escapeHtml(JSON.stringify(data.tool_traces))}'>
          ⚡ Tools Orchestrated: <strong>${toolsStr}</strong>
        </div>
      `;
    }

    let attachmentsHtml = "";
    if (data.attachments && data.attachments.length > 0) {
      data.attachments.forEach(att => {
        const icon = att.type === "pdf" ? "📄" : "📊";
        attachmentsHtml += `
          <div class="doc-attachment-card">
            <span class="doc-att-icon">${icon}</span>
            <div class="doc-att-info">
              <div class="doc-att-title">${att.title}</div>
              <div class="doc-att-sub">Official Generated Kirana Document</div>
            </div>
            <a href="${att.url}" target="_blank" download class="btn-att-download">
              Download ${att.type.toUpperCase()}
            </a>
          </div>
        `;
        addToFileLinks(att);
      });
    }

    msgDiv.innerHTML = `
      <div class="message-avatar">🤖</div>
      <div class="message-body">
        <div class="message-sender">Kirana Manager AI</div>
        <div class="message-content">
          ${formatMarkdown(data.reply)}
          ${attachmentsHtml}
        </div>
        ${toolTracesHtml}
      </div>
    `;
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function formatMarkdown(text) {
    if (!text) return "";
    let html = escapeHtml(text);
    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    // Italic
    html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
    // Linebreaks
    html = html.replace(/\n/g, "<br/>");
    // Bullet points
    html = html.replace(/•\s*(.*?)(?=(?:<br\/>|$))/g, "<li>$1</li>");
    return html;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function addToFileLinks(att) {
    if (generatedDocsList.some(d => d.title === att.title)) return;
    generatedDocsList.unshift(att);

    const icon = att.type === "pdf" ? "📄" : "📊";
    const item = document.createElement("div");
    item.className = "file-link-item";
    item.innerHTML = `
      <span>${icon} <strong>${att.title}</strong></span>
      <a href="${att.url}" target="_blank" download>Download</a>
    `;

    // Clear empty hint
    const emptyHint = fileLinks.querySelector(".empty-hint");
    if (emptyHint) emptyHint.remove();

    fileLinks.prepend(item);
  }

  // -------------------------------------------------------------
  // Panel Refreshers
  // -------------------------------------------------------------
  async function refreshAllPanels() {
    await Promise.all([
      refreshDraft(),
      refreshInventory(),
      refreshKhata(),
      refreshAnalytics()
    ]);
  }

  async function refreshDraft() {
    try {
      const res = await fetch("/api/draft");
      const draft = await res.json();
      renderDraftBill(draft);
    } catch (e) {
      console.error("Error fetching draft:", e);
    }
  }

  function renderDraftBill(draft) {
    badgeDraftCount.textContent = draft.items_count || 0;
    if (!draft.items || draft.items.length === 0) {
      draftItemsList.innerHTML = `
        <p class="empty-hint">Draft bill is currently empty.<br/>Try saying: <em>"Make a bill with 2kg sugar and 4 Maggi"</em></p>
      `;
      draftSummary.style.display = "none";
      return;
    }

    let rowsHtml = "";
    draft.items.forEach(it => {
      rowsHtml += `
        <div class="draft-item-row">
          <div>
            <div class="draft-item-name">${it.name}</div>
            <div class="draft-item-meta">${it.quantity} ${it.unit} @ ₹${it.selling_price} | GST: ${parseFloat(it.gst_rate).toFixed(0)}%</div>
          </div>
          <div class="draft-item-price">₹${parseFloat(it.line_total).toFixed(2)}</div>
        </div>
      `;
    });

    draftItemsList.innerHTML = rowsHtml;
    draftSubtotal.textContent = `₹${parseFloat(draft.subtotal).toFixed(2)}`;
    draftCgst.textContent = `₹${parseFloat(draft.total_cgst).toFixed(2)}`;
    draftSgst.textContent = `₹${parseFloat(draft.total_sgst).toFixed(2)}`;
    draftGrandTotal.textContent = `₹${parseFloat(draft.grand_total).toFixed(2)}`;
    draftPaymentMode.textContent = draft.payment_mode || "UPI";
    draftSummary.style.display = "flex";
  }

  async function refreshInventory() {
    try {
      const res = await fetch("/api/inventory");
      const data = await res.json();
      badgeStockCount.textContent = data.total_items || 0;

      let html = "";
      data.products.forEach(p => {
        const stockNum = parseFloat(p.stock);
        const isLow = stockNum <= 10;
        const tagClass = isLow ? "stock-tag stock-low" : "stock-tag stock-healthy";
        const typeBadge = p.is_loose ? `<span class="loose-badge">Loose</span>` : `<span class="sub-hint">Packaged</span>`;

        html += `
          <tr>
            <td>
              <strong>${p.name}</strong><br/>
              <span class="sub-hint">${p.sku} | ${p.brand || 'Generic'}</span>
            </td>
            <td>${typeBadge}</td>
            <td><span class="${tagClass}">${p.stock} ${p.unit}</span></td>
            <td><strong>₹${parseFloat(p.selling_price).toFixed(2)}</strong></td>
            <td>${parseFloat(p.gst_rate).toFixed(0)}%</td>
          </tr>
        `;
      });
      inventoryTbody.innerHTML = html;
    } catch (e) {
      console.error("Error fetching inventory:", e);
    }
  }

  async function refreshKhata() {
    try {
      const res = await fetch("/api/khata");
      const customers = await res.json();

      let html = "";
      customers.forEach(c => {
        html += `
          <div class="khata-card" data-customer="${c.name}">
            <div>
              <div class="khata-name">👤 ${c.name}</div>
              <div class="khata-phone">Tel: ${c.phone}</div>
            </div>
            <div class="khata-balance">₹${parseFloat(c.balance).toFixed(2)}</div>
          </div>
        `;
      });
      khataCards.innerHTML = html;

      // Card click opens customer ledger
      khataCards.querySelectorAll(".khata-card").forEach(card => {
        card.addEventListener("click", async () => {
          const cname = card.getAttribute("data-customer");
          await loadCustomerLedger(cname);
        });
      });
    } catch (e) {
      console.error("Error fetching khata:", e);
    }
  }

  async function loadCustomerLedger(customerName) {
    try {
      const res = await fetch(`/api/khata/${encodeURIComponent(customerName)}`);
      const data = await res.json();
      ledgerCustomerTitle.textContent = `${data.customer_name}'s Ledger (Balance: ₹${data.current_balance})`;

      let html = "";
      if (!data.ledger || data.ledger.length === 0) {
        html = "<p class='empty-hint'>No transactions recorded yet.</p>";
      } else {
        data.ledger.forEach(tx => {
          const isCredit = tx.type === "CREDIT";
          const typeClass = isCredit ? "ledger-credit" : "ledger-payment";
          const sign = isCredit ? "+" : "-";
          html += `
            <div class="ledger-entry-row">
              <div>
                <span class="${typeClass}"><strong>${sign}₹${parseFloat(tx.amount).toFixed(2)}</strong> [${tx.type}]</span><br/>
                <span class="sub-hint">${tx.date} • ${tx.notes || tx.reference}</span>
              </div>
              <div class="sub-hint">Bal: ₹${tx.running_balance}</div>
            </div>
          `;
        });
      }
      ledgerEntries.innerHTML = html;
      customerLedgerView.style.display = "block";
    } catch (e) {
      alert("Error loading ledger: " + e.message);
    }
  }

  async function refreshAnalytics() {
    try {
      const res = await fetch("/api/analytics");
      const data = await res.json();

      kpiSales.textContent = `₹${parseFloat(data.total_sales).toFixed(2)}`;
      kpiBills.textContent = `${data.bills_count} Invoices Finalized`;
      kpiGst.textContent = `₹${parseFloat(data.total_gst).toFixed(2)}`;
      kpiGstSplit.textContent = `CGST: ₹${data.total_cgst} | SGST: ₹${data.total_sgst}`;

      splitUpi.textContent = `₹${parseFloat(data.payment_modes.UPI).toFixed(2)}`;
      splitCash.textContent = `₹${parseFloat(data.payment_modes.CASH).toFixed(2)}`;
      splitCard.textContent = `₹${parseFloat(data.payment_modes.CARD).toFixed(2)}`;
    } catch (e) {
      console.error("Error fetching analytics:", e);
    }
  }

  // Initial load
  refreshAllPanels();
});

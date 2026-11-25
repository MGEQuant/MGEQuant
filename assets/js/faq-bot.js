(function () {
  "use strict";

  // Switches for the two support channels. Both stay OFF (greyed, "coming soon") until the owner turns them on:
  //   AI_ON    - "Ask anything": answers from an AI that only knows this site (needs the site chat route + an AI key).
  //   HUMAN_ON - "Talk to a human": shows our support e-mail address with copy buttons; a person replies by e-mail.
  var AI_ON = false;
  var HUMAN_ON = true;
  var SUPPORT = "support@mgequant.com";

  var FAQ = [
    {
      q: "What is MGEQuant?",
      a: "We build and test trading models — started on NQ futures, now across other indices, forex, crypto and equities — and publish what we find, including what fails. <a href=\"/Mission%20and%20Vision/\">Read our mission &rarr;</a>"
    },
    {
      q: "Do you sell trade signals or give advice?",
      a: "No trade signals, no personalized advice — that doesn't change. We're in the process of preparing some indicators and strategies as paid software licenses (tools you'd run yourself, not signals), but nothing is for sale yet. This site stays educational and research content only."
    },
    {
      q: "What's the research pipeline?",
      a: "Every idea goes: Idea &rarr; Hypothesis &rarr; Prototype &rarr; Backtest &rarr; Forward test &rarr; Break/refine &rarr; Document. Most ideas don't survive it — that's the point. <a href=\"/DevelopmentLogs/\">See the dev logs &rarr;</a>"
    },
    {
      q: "Where can I read the dev logs?",
      a: "All of them, organized by indicator and strategy: <a href=\"/DevelopmentLogs/\">Development Logs &rarr;</a>"
    },
    {
      q: "Can I see the tools on a real chart?",
      a: "Yes — chart captures and recordings, not mock-ups: <a href=\"/in-action.html\">Indicators in action &rarr;</a> or the <a href=\"/#charts\">chart gallery on the homepage &rarr;</a>."
    },
    {
      q: "What's the prop-firm calculator?",
      a: "A free tool that checks an account against its drawdown, consistency, payout and trading-day rules before you take a trade. <a href=\"/mgequant-propfirm-calculator.html\">Open the calculator &rarr;</a>"
    },
    {
      q: "How do I get the weekly research notes?",
      a: "They're free on Substack: <a href=\"https://mgequantnotes.substack.com\" target=\"_blank\" rel=\"noopener noreferrer\">mgequantnotes.substack.com &rarr;</a>"
    },
    {
      q: "Where do you post updates?",
      a: "X: <a href=\"https://x.com/MGEQuant\" target=\"_blank\" rel=\"noopener noreferrer\">@MGEQuant</a> &middot; Instagram: <a href=\"https://www.instagram.com/mgequant/\" target=\"_blank\" rel=\"noopener noreferrer\">@mgequant</a> &middot; all links: <a href=\"https://linktr.ee/mgequant\" target=\"_blank\" rel=\"noopener noreferrer\">linktr.ee/mgequant &rarr;</a>"
    }
  ];

  // Home screen: quick links shown under the search box.
  var LINKS = [
    { t: "Apply to test MGE Labs", h: "/labs.html#beta" },
    { t: "What is MGE Labs?", h: "/labs.html" },
    { t: "Does it support my broker?", h: "/brokers.html" },
    { t: "Terms of Service", h: "/terms.html" },
    { t: "Privacy Policy", h: "/privacy.html" }
  ];

  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  function init() {
    var btn = el("button", "mge-chat-btn", "&#128172;");
    btn.type = "button";
    btn.setAttribute("aria-label", "Open help chat");
    btn.setAttribute("aria-expanded", "false");

    var panel = el("div", "mge-chat-panel");
    panel.hidden = true;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "MGEQuant help");

    var head = el("div", "mge-chat-head");
    head.appendChild(el("span", "mge-chat-hello", "Hi there &#128075;<br>How can we help?"));
    var closeBtn = el("button", null, "&times;");
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", "Close help chat");
    head.appendChild(closeBtn);

    var body = el("div", "mge-chat-body");
    var foot = el("div", "mge-chat-foot", AI_ON ? "AI answers can be wrong. Never trade advice." : "Scripted answers, not an AI assistant — and not trade advice.");

    // Ask anything (AI) + Talk to a human. Shown greyed out until switched on above.
    var ask = el("form", "mge-chat-ask" + (AI_ON ? "" : " is-off"));
    var askInput = el("input");
    askInput.type = "text";
    askInput.maxLength = 300;
    askInput.placeholder = AI_ON ? "Ask anything about MGEQuant…" : "Ask anything (coming soon)";
    askInput.setAttribute("aria-label", "Ask a question");
    askInput.disabled = !AI_ON;
    var askBtn = el("button", null, "&#10148;");
    askBtn.type = "submit";
    askBtn.setAttribute("aria-label", "Send");
    askBtn.disabled = !AI_ON;
    ask.appendChild(askInput);
    ask.appendChild(askBtn);
    ask.addEventListener("submit", function (e) { e.preventDefault(); });

    var human = el("button", "mge-chat-human" + (HUMAN_ON ? "" : " is-off"),
      "&#128100; Talk to a human" + (HUMAN_ON ? "" : " <small>coming soon</small>"));
    human.type = "button";
    human.disabled = !HUMAN_ON;
    if (HUMAN_ON) human.addEventListener("click", function () { showHuman(); });

    var extra = el("div", "mge-chat-extra");
    extra.appendChild(ask);
    extra.appendChild(human);

    panel.appendChild(head);
    panel.appendChild(body);
    if (AI_ON) panel.appendChild(extra);
    panel.appendChild(foot);

    function showHome() {
      panel.classList.add("is-home");
      body.innerHTML = "";
      var contact = el("button", "mge-chat-card mge-chat-contact", "<span>Contact support</span><i aria-hidden=\"true\">&#10148;</i>");
      contact.type = "button";
      contact.addEventListener("click", showHuman);
      body.appendChild(contact);

      var card = el("div", "mge-chat-card");
      var form = el("form", "mge-chat-search");
      form.action = "/search.html";
      form.method = "get";
      var q = el("input");
      q.type = "search"; q.name = "q"; q.maxLength = 80; q.placeholder = "Search for help";
      q.setAttribute("aria-label", "Search the site");
      var go = el("button", null, "&#128269;");
      go.type = "submit"; go.setAttribute("aria-label", "Search");
      form.appendChild(q); form.appendChild(go);
      card.appendChild(form);
      LINKS.forEach(function (l) {
        var a = el("a", "mge-chat-row", "<span>" + l.t + "</span><i aria-hidden=\"true\">&rsaquo;</i>");
        a.href = l.h;
        card.appendChild(a);
      });
      var more = el("button", "mge-chat-row", "<span>Common questions</span><i aria-hidden=\"true\">&rsaquo;</i>");
      more.type = "button";
      more.addEventListener("click", showMenu);
      card.appendChild(more);
      body.appendChild(card);
    }

    function backBtn(label, fn) {
      var back = el("button", "mge-chat-back", "&larr; " + label);
      back.type = "button";
      back.addEventListener("click", fn);
      return back;
    }

    function showMenu() {
      panel.classList.remove("is-home");
      body.innerHTML = "";
      body.appendChild(el("p", null, "What do you want to know?"));
      FAQ.forEach(function (item) {
        var qBtn = el("button", "mge-chat-q", item.q);
        qBtn.type = "button";
        qBtn.addEventListener("click", function () { showAnswer(item); });
        body.appendChild(qBtn);
      });
      body.appendChild(backBtn("Back", showHome));
    }

    function showAnswer(item) {
      body.innerHTML = "";
      var ans = el("div", "mge-chat-answer");
      ans.innerHTML = "<b>" + item.q + "</b><p>" + item.a + "</p>";
      body.appendChild(ans);
      var back = el("button", "mge-chat-back", "&larr; Back to questions");
      back.type = "button";
      back.addEventListener("click", showMenu);
      body.appendChild(back);
    }

    function copyText(t, said) {
      function ok(m) { said.textContent = m; setTimeout(function () { said.textContent = ""; }, 3000); }
      function fallback() {
        var ta = document.createElement("textarea"); ta.value = t; ta.setAttribute("readonly", "");
        ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select();
        var done = false; try { done = document.execCommand("copy"); } catch (e) {}
        document.body.removeChild(ta);
        ok(done ? "Copied" : "Select the text and press Ctrl+C");
      }
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(t).then(function () { ok("Copied"); }, fallback);
      else fallback();
    }

    function showHuman() {
      panel.classList.remove("is-home");
      var start = "Hi MGEQuant,\n\nMy question:\n\n";
      body.innerHTML = "";
      var box = el("div", "mge-chat-answer mge-chat-mail");
      box.innerHTML = "<b>Talk to a person</b>" +
        "<p>Write to us by e-mail from any mailbox you use. A person reads every message and replies by e-mail.</p>" +
        "<p class=\"mge-chat-addr\"><span>" + SUPPORT + "</span> <button type=\"button\" class=\"mge-chat-copy\" data-c=\"a\">Copy address</button></p>" +
        "<p><button type=\"button\" class=\"mge-chat-copy\" data-c=\"t\">Copy a starter message</button> <span class=\"mge-chat-said\" aria-live=\"polite\"></span></p>" +
        "<p class=\"mge-chat-small\">Please do not send passwords, account numbers or screenshots that show your account. Questions only, no trade advice.</p>" +
        "<p class=\"mge-chat-small\">Use a mail app on this computer? <a href=\"mailto:" + SUPPORT + "?subject=" + encodeURIComponent("Question from the website") + "\">Open it there</a>.</p>";
      body.appendChild(box);
      var said = box.querySelector(".mge-chat-said");
      var cb = box.querySelectorAll(".mge-chat-copy");
      for (var i = 0; i < cb.length; i++) cb[i].addEventListener("click", function (e) {
        copyText(e.currentTarget.getAttribute("data-c") === "a" ? SUPPORT : start, said);
      });
      body.appendChild(backBtn("Back", showHome));
    }

    function open() {
      panel.hidden = false;
      btn.setAttribute("aria-expanded", "true");
    }
    function close() {
      panel.hidden = true;
      btn.setAttribute("aria-expanded", "false");
    }

    btn.addEventListener("click", function () {
      if (panel.hidden) { open(); } else { close(); }
    });
    closeBtn.addEventListener("click", close);

    showHome();
    document.body.appendChild(btn);
    document.body.appendChild(panel);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

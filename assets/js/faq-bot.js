(function () {
  "use strict";

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
    head.appendChild(el("span", null, "MGEQuant Help"));
    var closeBtn = el("button", null, "&times;");
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", "Close help chat");
    head.appendChild(closeBtn);

    var body = el("div", "mge-chat-body");
    var foot = el("div", "mge-chat-foot", "Scripted answers, not an AI assistant — and not trade advice.");

    panel.appendChild(head);
    panel.appendChild(body);
    panel.appendChild(foot);

    function showMenu() {
      body.innerHTML = "";
      body.appendChild(el("p", null, "What do you want to know?"));
      FAQ.forEach(function (item) {
        var qBtn = el("button", "mge-chat-q", item.q);
        qBtn.type = "button";
        qBtn.addEventListener("click", function () { showAnswer(item); });
        body.appendChild(qBtn);
      });
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

    showMenu();
    document.body.appendChild(btn);
    document.body.appendChild(panel);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

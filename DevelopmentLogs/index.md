---
layout: default
title: "Development Logs"
---

# Development Logs

What we built, tested, and learned — including what failed. New entries appear here automatically once pushed.

{% assign devlog_pages = site.pages | where_exp: "p", "p.url contains '/DevelopmentLogs/'" %}
{% assign devlog_pages = devlog_pages | where_exp: "p", "p.url != page.url" %}
{% assign devlog_pages = devlog_pages | sort: "url" %}

<ul>
{% for p in devlog_pages %}
  <li><a href="{{ p.url }}">{{ p.title | default: p.name }}</a></li>
{% endfor %}
</ul>

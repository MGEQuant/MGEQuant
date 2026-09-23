---
layout: default
title: "Development Logs"
---

# Development Logs

What we built, tested, and learned — including what failed. New entries appear here automatically once pushed.

{% assign devlog_pages = site.pages | where_exp: "p", "p.url contains '/DevelopmentLogs/'" %}
{% assign devlog_pages = devlog_pages | where_exp: "p", "p.url != page.url" %}
{% assign devlog_dated = devlog_pages | where_exp: "p", "p.date != nil" %}
{% assign devlog_dated = devlog_dated | sort: "date" | reverse %}
{% assign devlog_undated = devlog_pages | where_exp: "p", "p.date == nil" %}
{% assign devlog_pages = devlog_dated | concat: devlog_undated %}

<ul class="log-list">
{% for p in devlog_pages %}
  <li><a href="{{ p.url }}">{{ p.title | default: p.name }}</a>{% if p.date %} <time>{{ p.date | date: "%b %-d, %Y" }}</time>{% endif %}</li>
{% endfor %}
</ul>

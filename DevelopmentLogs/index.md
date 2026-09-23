---
layout: default
title: "Development Logs"
---

# Development Logs

What we built, tested, and learned — including what failed. New entries appear here automatically once pushed.

{% assign devlog_pages = site.pages | where_exp: "p", "p.url contains '/DevelopmentLogs/'" %}
{% assign devlog_pages = devlog_pages | where_exp: "p", "p.url != page.url" %}
{% assign devlog_pages = devlog_pages | sort: "url" %}
{% assign grouped = devlog_pages | group_by_exp: "p", "p.url | split: '/' | slice: 2, 1 | first" %}

<div class="card-row">
{% for group in grouped %}
  <div class="card">
    <h3>{{ group.name }}</h3>
    <ul>
    {% for p in group.items %}
      <li><a href="{{ p.url }}">{{ p.title | default: p.name }}</a></li>
    {% endfor %}
    </ul>
  </div>
{% endfor %}
</div>

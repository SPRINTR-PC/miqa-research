# Customize Allauth LoginView for HTMX Support

Part of: wayfinder-htmx-login-map

## Question

How should we override allauth's LoginView to serve different templates for HTMX vs regular requests?

The current setup uses allauth's built-in LoginView which serves `account/login.{TEMPLATE_EXTENSION}`. We need it to serve `account/login.html` for regular requests and `account/login.partial.html` for HTMX requests.

Options to consider:
1. Subclass allauth's LoginView and override `get_template_names()`
2. Create a completely custom login view
3. Use Django middleware to swap templates
4. Override the template_name attribute conditionally in dispatch

What's the cleanest approach that aligns with the project's architecture?

## Type
research

## Status
open
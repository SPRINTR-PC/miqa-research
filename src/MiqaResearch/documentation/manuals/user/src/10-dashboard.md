# The Dashboard

<!-- PROTOTYPE stub page for the manual layout prototype (#233). Not real content. -->

The dashboard shows one tab per area of a project.

## Consent statistics

Shows how many participants have consented, per site and over time.

## Goals

Shows progress towards each Data Collection Goal. A goal can be scoped to one site.

### Reading the goal chart

Bars fill as data arrives. A dashed line marks the target.

```python
# Example: nothing to run here, just a code block to style.
goal = project.goals.first()
print(goal.progress)
```

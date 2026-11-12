"""Django-free ETL sandbox package (#412): the script contract, the Python and R shims, and the Datatype
row schemas. Imports no Django or Celery (`MiqaResearch/__init__.py` imports the Celery app, so nothing in
here may import `MiqaResearch`) -- the sandbox image copies only this package. Entrypoint:
`python -m mires_etl [root]`."""

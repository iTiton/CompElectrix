import os
import tempfile

# Antes de importar la app: base de datos temporal y sin tareas en segundo plano
os.environ.setdefault("COMPELECTRIX_DATA", tempfile.mkdtemp())
os.environ["COMPELECTRIX_SIN_TAREAS"] = "1"

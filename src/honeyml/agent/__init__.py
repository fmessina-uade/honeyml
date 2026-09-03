"""Motor de triaje agéntico.

Consume eventos normalizados del bus, arma el contexto, le pide a un servicio de inferencia que los
clasifique, valida la respuesta contra un esquema cerrado y persiste la decisión.

La estructura sigue la vista de desarrollo: un módulo por responsabilidad, así las piezas que
concentran el riesgo (la validación del esquema y el adaptador del proveedor) quedan aisladas y se
pueden reemplazar.
"""

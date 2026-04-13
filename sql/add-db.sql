INSERT INTO "T_OTRI_PI_ESTADOS" ("IDOTRIPIESTADOS", "DESCRIPCION", "ULTIMO_CAMBIO") VALUES
(1,  'Novedad probable', CURRENT_TIMESTAMP),
(2,  'Revisar (zonas grises, semejanza moderada)', CURRENT_TIMESTAMP),
(3,  'No novedoso (colisión probable)', CURRENT_TIMESTAMP),
(4,  'Riesgo: nivel inventivo bajo (obviedad probable)', CURRENT_TIMESTAMP),
(5,  'Riesgo intermedio (posible obviedad)', CURRENT_TIMESTAMP),
(6,  'Nivel inventivo probable (no-obvio)', CURRENT_TIMESTAMP),
(7,  'Insuficiente evidencia (pocas coincidencias)', CURRENT_TIMESTAMP),
(8,  'Aplicación industrial probable', CURRENT_TIMESTAMP),
(9,  'Revisar (evidencia limitada)', CURRENT_TIMESTAMP),
(10, 'No aplica', CURRENT_TIMESTAMP),
(11, 'Evaluación basada solo en palabras clave', CURRENT_TIMESTAMP),
(12, 'PENDIENTE', CURRENT_TIMESTAMP),
(13, 'PROCESANDO', CURRENT_TIMESTAMP),
(14, 'COMPLETADO', CURRENT_TIMESTAMP),
(15, 'FALLIDO', CURRENT_TIMESTAMP)
ON CONFLICT ("IDOTRIPIESTADOS") DO NOTHING;
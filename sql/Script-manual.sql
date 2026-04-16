ALTER TABLE "OTRI"."T_OTRI_PI_PROCESO" ADD COLUMN IF NOT EXISTS "KEYWORDS" text;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'OTRI'
  AND table_name = 'T_OTRI_PI_PROCESO'
ORDER BY ordinal_position;
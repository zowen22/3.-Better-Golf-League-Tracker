-- Adds mobile/tablet/desktop classification to traffic_events, derived
-- from user_agent at write time. See app/traffic.py's _device_type().
ALTER TABLE traffic_events ADD COLUMN IF NOT EXISTS device_type TEXT;

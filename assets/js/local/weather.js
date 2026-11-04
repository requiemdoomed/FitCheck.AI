// Today's weather for the generator, from Open-Meteo (open source, free,
// no key: open-meteo.com). Only asked for when the person presses the button;
// the location is rounded to about 1 km before it leaves the device and is
// never stored.
// Swayam Shakya

const API = "https://api.open-meteo.com/v1/forecast";

/** WMO weather code + wind -> FitCheck.AI's weather words. */
export function weatherWord(code, windKmh = 0) {
  const c = Number(code);
  if ([71, 73, 75, 77, 85, 86].includes(c)) return "snowy";
  if ((c >= 51 && c <= 67) || (c >= 80 && c <= 82) || c >= 95) return "rainy";
  if (windKmh >= 30) return "windy";
  if (c <= 1) return "sunny";
  return "cloudy";
}

export class WeatherError extends Error {}

function position() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new WeatherError("This browser can't share its location."));
    navigator.geolocation.getCurrentPosition(
      (p) => resolve(p.coords),
      (e) => reject(new WeatherError(e.code === 1 ? "Location wasn't allowed, so the weather couldn't be filled in." : "Couldn't find your location.")),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 30 * 60 * 1000 },
    );
  });
}

/** { weather, temperature_c, place } for the current location. */
export async function localWeather() {
  const { latitude, longitude } = await position();
  const q = new URLSearchParams({
    latitude: latitude.toFixed(2), longitude: longitude.toFixed(2),
    current: "temperature_2m,weather_code,wind_speed_10m", timezone: "auto",
  });
  let data;
  try {
    const res = await fetch(`${API}?${q}`);
    if (!res.ok) throw new Error(String(res.status));
    data = await res.json();
  } catch {
    throw new WeatherError("Couldn't reach the weather service. Set the weather by hand.");
  }
  const cur = data.current || {};
  const t = Number(cur.temperature_2m);
  if (!Number.isFinite(t)) throw new WeatherError("The weather service didn't send a temperature.");
  return { weather: weatherWord(cur.weather_code, Number(cur.wind_speed_10m) || 0), temperature_c: Math.round(t) };
}

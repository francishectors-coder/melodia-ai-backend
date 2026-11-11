
FROM python:3.11-slim-bookworm

# Install FFmpeg, FluidSynth and the General MIDI SoundFont.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg \
       libfluidsynth3 \
       fluid-soundfont-gm \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install existing Python dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy MELODIA AI application files.
COPY . .

# Make the system SoundFont available at the path expected by V5.
RUN mkdir -p /app/soundfonts \
    && ln -s /usr/share/sounds/sf2/FluidR3_GM.sf2 \
       /app/soundfonts/FluidR3_GM.sf2

# Render supplies the PORT environment variable.
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

EXPOSE 10000

# Start the existing Flask application through Gunicorn.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} melodia_web_server:app"]

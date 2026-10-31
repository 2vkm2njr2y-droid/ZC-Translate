export const store = {
  settings: {},
  models: [],
  activeProfile: "balanced",
  engine: {},
  system: null,
  glossaries: [],
  doctor: null,
  streaming: false,
  jobId: "",
  lastMeta: null,
  lastDetected: "",
  draftText: "",
  draftTarget: "",
  listeners: new Set(),

  set(patch) {
    Object.assign(this, patch);
    for (const listener of this.listeners) {
      try {
        listener(this);
      } catch (error) {
        console.error(error);
      }
    }
  },

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  },

  activeModel() {
    return this.models.find((item) => item.profile_id === this.settings.profile_id) || null;
  },

  hasModel() {
    return this.models.some((item) => item.installed);
  },
};

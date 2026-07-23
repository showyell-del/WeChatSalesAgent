const PHASE0_TEXT_SEND_TARGET = "filehelper";

rpc.exports = {
  manifest: function () {
    return {
      target: PHASE0_TEXT_SEND_TARGET,
      scope: "phase0_text_only_manual_smoke",
      requiredEvidence: "visible_ack_cleanup"
    };
  }
};

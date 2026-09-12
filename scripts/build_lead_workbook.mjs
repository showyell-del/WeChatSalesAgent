import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [snapshotPath, outputPath] = process.argv.slice(2);
if (!snapshotPath || !outputPath) {
  throw new Error("usage: build_lead_workbook.mjs <snapshot.json|-> <output.xlsx>");
}

async function readSnapshot() {
  if (snapshotPath !== "-") return fs.readFile(snapshotPath, "utf8");
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

const snapshot = JSON.parse(await readSnapshot());
const isPublishedAnalysis = snapshot.schema_version === "workspace.v2";
const isAgentQuery = snapshot.schema_version === "agent.query.v1";
const isSmartAnalysis = snapshot.schema_version === "agent.query.v2";
if ((!isPublishedAnalysis && !isAgentQuery && !isSmartAnalysis) || !Array.isArray(snapshot.leads) || snapshot.leads.length === 0) {
  throw new Error("LEAD_RESULT_SNAPSHOT_REQUIRED");
}

const formulaErrors = ["#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!", "#SPILL!", "#CALC!"];

async function saveVerifiedWorkbook(workbook, sheetPreviews) {
  await workbook.recalculate();
  const inspections = [];
  for (const preview of sheetPreviews) inspections.push(await workbook.inspect({ kind: "table", range: `${preview.sheetName}!${preview.range}`, include: "values,formulas", tableMaxRows: 24, tableMaxCols: 20 }));
  const errorCheck = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" });
  if (formulaErrors.some((error) => errorCheck.ndjson.includes(error))) throw new Error("WORKBOOK_FORMULA_ERROR");
  if (process.env.PHASE4_VERIFY_DIR) {
    await fs.mkdir(process.env.PHASE4_VERIFY_DIR, { recursive: true });
    for (const preview of sheetPreviews) {
      const image = await workbook.render({ sheetName: preview.sheetName, range: preview.range, scale: 1.2, format: "png" });
      await fs.writeFile(`${process.env.PHASE4_VERIFY_DIR}/${preview.fileName}`, new Uint8Array(await image.arrayBuffer()));
    }
    await fs.writeFile(`${process.env.PHASE4_VERIFY_DIR}/formula-errors.ndjson`, errorCheck.ndjson);
    await fs.writeFile(`${process.env.PHASE4_VERIFY_DIR}/key-ranges.ndjson`, inspections.map((item) => item.ndjson).join("\n"));
  }
  const outputDir = outputPath.slice(0, outputPath.lastIndexOf("/"));
  if (outputDir) await fs.mkdir(outputDir, { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outputPath);
  await fs.rm(`${outputPath}.inspect.ndjson`, { force: true });
}

if (isSmartAnalysis) {
  const options = {
    include_evidence: true,
    include_statistics: true,
    include_followups: true,
    include_chart: true,
    ...(snapshot.report_options || {}),
  };
  const workbook = Workbook.create();
  const summary = workbook.worksheets.add("分析结果");
  const taskSheetNames = {
    customer_search: "客户清单",
    opportunity_analysis: "机会清单",
    reengagement_analysis: "激活建议",
    customer_risk: "风险清单",
    commitment_tracker: "承诺待办",
    person_profile: "人物画像",
    relationship_insight: "关系洞察",
    comparison: "多人比较",
    topic_analysis: "话题分析",
    timeline: "事件时间线",
    general_search: "相关结果",
  };
  const detailName = taskSheetNames[snapshot.task_type];
  if (!detailName) throw new Error("UNKNOWN_ANALYSIS_TASK_TYPE");
  const detail = workbook.worksheets.add(detailName);
  const evidenceSheet = options.include_evidence ? workbook.worksheets.add("证据明细") : null;
  const statisticsSheet = options.include_statistics ? workbook.worksheets.add("互动统计") : null;
  for (const sheet of [summary, detail, evidenceSheet, statisticsSheet].filter(Boolean)) sheet.showGridLines = false;

  const navy = "#172554";
  const blue = "#2563EB";
  const paleBlue = "#EFF6FF";
  const border = "#CBD5E1";
  const title = snapshot.result_title || "智能分析结果";
  summary.getRange("A1:H2").merge();
  summary.getRange("A1").values = [[title]];
  summary.getRange("A1:H2").format = { font: { bold: true, color: navy, size: 22 }, verticalAlignment: "center" };
  summary.getRange("A3:H3").merge();
  summary.getRange("A3").values = [[`账号 ${snapshot.account_id || ""} · ${snapshot.query || ""} · 模型 ${(snapshot.run || {}).model || ""}`]];
  summary.getRange("A3:H3").format = { fill: paleBlue, font: { color: "#334155" }, wrapText: true };
  summary.getRange("A5:H5").merge();
  summary.getRange("A5").values = [["核心回答"]];
  summary.getRange("A5:H5").format = { fill: blue, font: { bold: true, color: "#FFFFFF" } };
  summary.getRange("A6:H7").merge();
  summary.getRange("A6").values = [[snapshot.answer || ""]];
  summary.getRange("A6:H7").format = { fill: "#FFFFFF", font: { color: "#1E293B", size: 13 }, borders: { preset: "outside", style: "thin", color: border }, wrapText: true, verticalAlignment: "top" };

  const sections = Array.isArray(snapshot.sections) ? snapshot.sections : [];
  let summaryRow = 9;
  if (sections.length) {
    summary.getRange(`A${summaryRow}:B${summaryRow}`).merge();
    summary.getRange(`C${summaryRow}:E${summaryRow}`).merge();
    summary.getRange(`A${summaryRow}`).values = [["分析维度"]];
    summary.getRange(`C${summaryRow}`).values = [["分析结论"]];
    summary.getRange(`F${summaryRow}:H${summaryRow}`).values = [["置信度", "支持证据", "反例证据"]];
    summary.getRange(`A${summaryRow}:H${summaryRow}`).format = { fill: navy, font: { bold: true, color: "#FFFFFF" } };
    summaryRow += 1;
    for (const section of sections) {
      summary.getRange(`A${summaryRow}:B${summaryRow}`).merge();
      summary.getRange(`C${summaryRow}:E${summaryRow}`).merge();
      summary.getRange(`A${summaryRow}`).values = [[section.title || "分析"]];
      summary.getRange(`C${summaryRow}`).values = [[section.content || ""]];
      summary.getRange(`F${summaryRow}`).values = [[`${section.confidence ?? 0}%`]];
      summary.getRange(`G${summaryRow}`).values = [[(section.evidence_ids || []).join("、")]];
      summary.getRange(`H${summaryRow}`).values = [[(section.counter_evidence_ids || []).join("、")]];
      summary.getRange(`A${summaryRow}:H${summaryRow}`).format = { borders: { preset: "inside", style: "thin", color: "#E2E8F0" }, wrapText: true, verticalAlignment: "top", rowHeight: 46 };
      summary.getRange(`A${summaryRow}:B${summaryRow}`).format.font = { bold: true, color: navy };
      summaryRow += 1;
    }
  }
  const followups = options.include_followups && Array.isArray(snapshot.suggested_followups) ? snapshot.suggested_followups : [];
  if (followups.length) {
    summaryRow += 1;
    summary.getRange(`A${summaryRow}:H${summaryRow}`).merge();
    summary.getRange(`A${summaryRow}`).values = [["可以继续分析"]];
    summary.getRange(`A${summaryRow}:H${summaryRow}`).format = { fill: paleBlue, font: { bold: true, color: navy } };
    summaryRow += 1;
    for (let index = 0; index < followups.length; index += 1) {
      summary.getRange(`A${summaryRow}:H${summaryRow}`).merge();
      summary.getRange(`A${summaryRow}`).values = [[`${index + 1}. ${followups[index]}`]];
      summaryRow += 1;
    }
  }
  summary.getRange(`A1:H${summaryRow}`).format.font.name = "PingFang SC";
  summary.getRange(`A1:H${summaryRow}`).format.columnWidth = 16;
  summary.getRange(`C1:G${summaryRow}`).format.columnWidth = 20;

  let headers;
  let rows;
  let detailWidths;
  const insightText = (item) => (item.insights || []).map((insight) => `${insight.label}：${insight.value}`).join("\n");
  const confidenceText = (item) => (item.insights || []).map((insight) => `${insight.label} ${insight.confidence ?? 0}%`).join("\n");
  const supportText = (item) => [...new Set((item.insights || []).flatMap((insight) => insight.evidence_ids || []))].join("、") || (item.evidence || []).map((e) => e.evidence_id).join("、");
  const counterText = (item) => [...new Set((item.insights || []).flatMap((insight) => insight.counter_evidence_ids || []))].join("、");
  const recentDate = (item) => item.recent_contact_ts ? new Date(item.recent_contact_ts * 1000) : "";
  let detailDateColumn = "";
  if (snapshot.task_type === "customer_search") {
    headers = ["客户名称", "客户ID", "成交意向分", "意向阶段", "最近联系", "明确需求", "阻碍因素", "联系方式", "建议动作", "核心结论", "结论置信度", "支持证据", "反例证据"];
    rows = snapshot.leads.map((item) => [item.display_name, item.customer_id, item.score, item.status_label, recentDate(item), item.need, item.obstacles, item.contact, item.suggested_action, item.summary, confidenceText(item), supportText(item), counterText(item)]);
    detailWidths = [16, 22, 12, 14, 19, 24, 24, 20, 28, 36, 22, 28, 28];
    detailDateColumn = "E";
  } else if (snapshot.task_type === "opportunity_analysis") {
    headers = ["联系人", "联系人ID", "机会强度", "机会阶段", "机会信号", "阻碍因素", "建议推进动作", "联系方式", "最近联系", "核心结论", "结论置信度", "支持证据", "反例证据"];
    rows = snapshot.leads.map((item) => [item.display_name, item.customer_id, item.score, item.status_label, insightText(item), item.obstacles, item.suggested_action, item.contact, recentDate(item), item.summary, confidenceText(item), supportText(item), counterText(item)]);
    detailWidths = [16, 22, 12, 14, 38, 24, 30, 20, 19, 34, 22, 28, 28];
    detailDateColumn = "I";
  } else if (snapshot.task_type === "reengagement_analysis") {
    headers = ["联系人", "联系人ID", "激活优先级", "触达建议", "沉默与激活信号", "最近联系", "互动总量", "活跃天数", "建议动作", "阻碍因素", "结论置信度", "支持证据", "反例证据"];
    rows = snapshot.leads.map((item) => [item.display_name, item.customer_id, item.score, item.status_label, insightText(item), recentDate(item), item.conversation_stats?.message_count || 0, item.conversation_stats?.active_days || 0, item.suggested_action, item.obstacles, confidenceText(item), supportText(item), counterText(item)]);
    detailWidths = [16, 22, 14, 14, 42, 19, 12, 12, 30, 24, 22, 28, 28];
    detailDateColumn = "F";
  } else if (snapshot.task_type === "customer_risk") {
    headers = ["联系人", "联系人ID", "风险严重度", "风险等级", "风险信号", "阻碍与客诉", "建议处理动作", "最近联系", "核心结论", "结论置信度", "支持证据", "反例证据"];
    rows = snapshot.leads.map((item) => [item.display_name, item.customer_id, item.score, item.status_label, insightText(item), item.obstacles, item.suggested_action, recentDate(item), item.summary, confidenceText(item), supportText(item), counterText(item)]);
    detailWidths = [16, 22, 14, 14, 42, 28, 32, 19, 34, 22, 28, 28];
    detailDateColumn = "H";
  } else if (snapshot.task_type === "person_profile") {
    headers = ["联系人", "联系人ID", "核心结论", "分析维度", "观察", "置信度", "消息总量", "对方消息", "我方消息", "活跃天数", "首次联系", "最近联系", "支持证据", "反例证据"];
    rows = snapshot.leads.flatMap((item) => {
      const stats = item.conversation_stats || {};
      const insights = Array.isArray(item.insights) && item.insights.length ? item.insights : [{ label: "结论", value: item.summary || "", evidence_ids: (item.evidence || []).map((e) => e.evidence_id) }];
      return insights.map((insight) => [item.display_name, item.customer_id, item.headline, insight.label, insight.value, `${insight.confidence ?? 0}%`, stats.message_count || 0, stats.incoming_count || 0, stats.outgoing_count || 0, stats.active_days || 0, stats.first_contact || "", stats.last_contact || "", (insight.evidence_ids || []).join("、"), (insight.counter_evidence_ids || []).join("、")]);
    });
    detailWidths = [16, 22, 28, 18, 42, 12, 14, 14, 14, 14, 21, 21, 28, 28];
  } else if (snapshot.task_type === "relationship_insight") {
    headers = ["联系人", "关系维度", "互动观察", "置信度", "互动总量", "对方消息", "我方消息", "活跃天数", "最近联系", "支持证据", "反例证据"];
    rows = snapshot.leads.flatMap((item) => (item.insights || []).map((insight) => {
      const stats = item.conversation_stats || {};
      return [item.display_name, insight.label, insight.value, `${insight.confidence ?? 0}%`, stats.message_count || 0, stats.incoming_count || 0, stats.outgoing_count || 0, stats.active_days || 0, stats.last_contact || item.recent_contact || "", (insight.evidence_ids || []).join("、"), (insight.counter_evidence_ids || []).join("、")];
    }));
    detailWidths = [18, 20, 46, 12, 12, 12, 12, 12, 20, 28, 28];
  } else if (["timeline", "commitment_tracker"].includes(snapshot.task_type)) {
    headers = ["类型", "对象", "日期", "状态", "负责人", "事项", "证据编号"];
    rows = (snapshot.structured_items || []).map((item) => [item.type, item.subject, item.date, item.status, item.owner, item.content, (item.evidence_ids || []).join("、")]);
    detailWidths = [14, 18, 20, 14, 16, 56, 28];
  } else {
    headers = snapshot.task_type === "topic_analysis" ? ["联系人", "话题维度", "分析结论", "置信度", "核心摘要", "最近联系", "支持证据", "反例证据"] : ["联系人", "分析维度", "分析结论", "置信度", "核心摘要", "最近联系", "支持证据", "反例证据"];
    rows = snapshot.leads.flatMap((item) => (item.insights || []).map((insight) => [item.display_name, insight.label, insight.value, `${insight.confidence ?? 0}%`, item.summary, item.recent_contact, (insight.evidence_ids || []).join("、"), (insight.counter_evidence_ids || []).join("、")]));
    detailWidths = [18, 20, 46, 12, 36, 20, 28, 28];
  }
  if (!rows.length) throw new Error("ANALYSIS_DETAIL_REQUIRED");
  detail.getRangeByIndexes(0, 0, 1, headers.length).values = [headers];
  detail.getRangeByIndexes(1, 0, rows.length, headers.length).values = rows;
  const detailLastRow = rows.length + 1;
  const detailLastColumn = String.fromCharCode(64 + headers.length);
  const detailTable = detail.tables.add(`A1:${detailLastColumn}${detailLastRow}`, true, "SmartAnalysisTable");
  detailTable.style = "TableStyleMedium2";
  detailTable.showFilterButton = true;
  detail.freezePanes.freezeRows(1);
  detail.freezePanes.freezeColumns(2);
  detail.getRange(`A1:${detailLastColumn}1`).format = { fill: navy, font: { bold: true, color: "#FFFFFF" }, rowHeight: 30 };
  detail.getRange(`A2:${detailLastColumn}${detailLastRow}`).format = { wrapText: true, verticalAlignment: "top", rowHeight: 48 };
  if (detailDateColumn) detail.getRange(`${detailDateColumn}2:${detailDateColumn}${detailLastRow}`).format.numberFormat = "yyyy-mm-dd hh:mm";
  if (snapshot.task_type === "person_profile") detail.getRange(`F2:J${detailLastRow}`).format.horizontalAlignment = "center";
  detailWidths.forEach((width, index) => { detail.getRangeByIndexes(0, index, detailLastRow, 1).format.columnWidth = width; });
  detail.getRange(`A1:${detailLastColumn}${detailLastRow}`).format.font.name = "PingFang SC";

  const evidenceRows = [];
  const seenEvidence = new Set();
  for (const item of snapshot.leads) {
    for (const evidence of item.evidence || []) {
      if (seenEvidence.has(evidence.evidence_id)) continue;
      seenEvidence.add(evidence.evidence_id);
      const context = (evidence.context || []).map((message) => `${message.is_target ? "▶" : " "} ${message.time} [${message.direction}] ${message.sender}: ${message.content}`).join("\n");
      evidenceRows.push([item.display_name, evidence.evidence_id, evidence.time, evidence.direction, evidence.sender, evidence.content, context]);
    }
  }
  let evidenceLastRow = 0;
  if (evidenceSheet) {
    if (!evidenceRows.length) throw new Error("ANALYSIS_EVIDENCE_REQUIRED");
    const evidenceHeaders = ["联系人", "证据编号", "时间", "方向", "发送者", "原始内容", "前后消息"];
    evidenceSheet.getRange("A1:G1").values = [evidenceHeaders];
    evidenceSheet.getRangeByIndexes(1, 0, evidenceRows.length, evidenceHeaders.length).values = evidenceRows;
    evidenceLastRow = evidenceRows.length + 1;
    const evidenceTable = evidenceSheet.tables.add(`A1:G${evidenceLastRow}`, true, "EvidenceDetailTable");
    evidenceTable.style = "TableStyleMedium2";
    evidenceSheet.freezePanes.freezeRows(1);
    evidenceSheet.getRange(`A1:G1`).format = { fill: navy, font: { bold: true, color: "#FFFFFF" }, rowHeight: 30 };
    evidenceSheet.getRange(`A2:G${evidenceLastRow}`).format = { wrapText: true, verticalAlignment: "top", rowHeight: 64 };
    [16, 28, 19, 12, 16, 56, 72].forEach((width, index) => { evidenceSheet.getRangeByIndexes(0, index, evidenceLastRow, 1).format.columnWidth = width; });
    evidenceSheet.getRange(`A1:G${evidenceLastRow}`).format.font.name = "PingFang SC";
  }

  let statisticsLastRow = 0;
  if (statisticsSheet) {
    const statisticHeaders = ["联系人", "消息总量", "对方消息", "我方消息", "活跃天数", "对方发起", "我方发起", "对方中位回复(分钟)", "我方中位回复(分钟)", "首次联系", "最近联系"];
    const statisticRows = snapshot.leads.map((item) => {
      const stats = item.conversation_stats || {};
      return [item.display_name, stats.message_count || 0, stats.incoming_count || 0, stats.outgoing_count || 0, stats.active_days || 0, stats.their_conversation_starts || 0, stats.my_conversation_starts || 0, stats.their_median_response_minutes ?? "", stats.my_median_response_minutes ?? "", stats.first_contact || "", stats.last_contact || ""];
    });
    if (statisticRows.length) {
      statisticsSheet.getRangeByIndexes(0, 0, 1, statisticHeaders.length).values = [statisticHeaders];
      statisticsSheet.getRangeByIndexes(1, 0, statisticRows.length, statisticHeaders.length).values = statisticRows;
      statisticsLastRow = statisticRows.length + 1;
      const statisticsTable = statisticsSheet.tables.add(`A1:K${statisticsLastRow}`, true, "InteractionStatsTable");
      statisticsTable.style = "TableStyleMedium2";
      statisticsSheet.freezePanes.freezeRows(1);
      statisticsSheet.getRange(`A1:K1`).format = { fill: navy, font: { bold: true, color: "#FFFFFF" }, rowHeight: 30 };
      statisticsSheet.getRange(`A2:K${statisticsLastRow}`).format.rowHeight = 28;
      [18, 12, 12, 12, 12, 12, 12, 20, 20, 20, 20].forEach((width, index) => { statisticsSheet.getRangeByIndexes(0, index, statisticsLastRow, 1).format.columnWidth = width; });
      statisticsSheet.getRange(`A1:K${statisticsLastRow}`).format.font.name = "PingFang SC";
      if (options.include_chart && statisticRows.length > 1) {
        const chart = statisticsSheet.charts.add("bar", [statisticsSheet.getRange(`A1:A${statisticsLastRow}`), statisticsSheet.getRange(`B1:B${statisticsLastRow}`)]);
        chart.title = "各联系人互动消息量";
        chart.titleTextStyle.fontSize = 12;
        chart.hasLegend = false;
        chart.setPosition("M2", "T18");
      }
    }
  }

  const previews = [
    { sheetName: "分析结果", range: `A1:H${Math.min(summaryRow, 24)}`, fileName: "analysis-summary.png" },
    { sheetName: detailName, range: `A1:${detailLastColumn}${Math.min(detailLastRow, 10)}`, fileName: "analysis-detail.png" },
  ];
  if (evidenceSheet) previews.push({ sheetName: "证据明细", range: `A1:G${Math.min(evidenceLastRow, 10)}`, fileName: "analysis-evidence.png" });
  if (statisticsSheet && statisticsLastRow) previews.push({ sheetName: "互动统计", range: options.include_chart && statisticsLastRow > 2 ? "A1:T18" : `A1:K${Math.min(statisticsLastRow, 10)}`, fileName: "analysis-statistics.png" });
  await saveVerifiedWorkbook(workbook, previews);
  process.exit(0);
}
const run = snapshot.run || {};
const metrics = snapshot.metrics || {};
const distribution = metrics.distribution || {};
const queryLabel = isAgentQuery ? `任务：${snapshot.query || "客户研究"}` : `分析批次 ${run.run_id || ""}`;

const workbook = Workbook.create();
const dashboard = workbook.worksheets.add("分析概览");
const leads = workbook.worksheets.add("客户激活表");
dashboard.showGridLines = false;
leads.showGridLines = false;

const navy = "#172554";
const blue = "#2563EB";
const paleBlue = "#EFF6FF";
const light = "#F8FAFC";
const border = "#CBD5E1";
const green = "#047857";
const amber = "#B45309";
const red = "#B91C1C";

dashboard.getRange("A1:H2").merge();
dashboard.getRange("A1").values = [[isAgentQuery ? "DeepSeek 客户研究结果" : "微信客户激活分析"]];
dashboard.getRange("A1:H2").format = {
  fill: navy,
  font: { bold: true, color: "#FFFFFF", size: 22 },
  verticalAlignment: "center",
};
dashboard.getRange("A3:H3").merge();
dashboard.getRange("A3").values = [[`账号 ${snapshot.account_id || ""} · ${queryLabel} · 模型 ${run.model || ""}`]];
dashboard.getRange("A3:H3").format = { fill: paleBlue, font: { color: "#334155" } };

const cardLabels = [["线索客户", "高意向", "待激活", "近30天联系"]];
dashboard.getRange("A5:G5").values = [[cardLabels[0][0], "", cardLabels[0][1], "", cardLabels[0][2], "", cardLabels[0][3]]];
dashboard.getRange("A6:G7").values = [[metrics.customer_total || 0, "", metrics.high_intent || 0, "", metrics.activation_needed || 0, "", metrics.recent_leads || 0], ["", "", "", "", "", "", ""]];
for (const range of ["A5:B7", "C5:D7", "E5:F7", "G5:H7"]) {
  dashboard.getRange(range).format = { fill: "#FFFFFF", borders: { preset: "outside", style: "thin", color: border } };
}
dashboard.getRange("A5:H5").format.font = { bold: true, color: "#64748B" };
dashboard.getRange("A6:H6").format.font = { bold: true, color: navy, size: 20 };
dashboard.getRange("A5:H5").format.rowHeight = 24;
dashboard.getRange("A6:H6").format.rowHeight = 34;
dashboard.getRange("A5:H7").format.verticalAlignment = "center";

dashboard.getRange("A9:D9").values = [["意向等级", "人数", "占比", "业务动作"]];
dashboard.getRange("A9:D9").format = { fill: blue, font: { bold: true, color: "#FFFFFF" } };
const bands = [
  ["高意向", distribution["高意向"] || 0, "优先当天跟进"],
  ["待激活", distribution["待激活"] || 0, "个性化重新激活"],
  ["长期培育", distribution["长期培育"] || 0, "低频维护"],
  ["排除", distribution["排除"] || 0, "不触达"],
];
dashboard.getRange("A10:B13").values = bands.map((item) => item.slice(0, 2));
dashboard.getRange("D10:D13").values = bands.map((item) => [item[2]]);
dashboard.getRange("C10").formulas = [["=IF($A$6=0,0,B10/$A$6)"]];
dashboard.getRange("C10:C13").fillDown();
dashboard.getRange("C10:C13").format.numberFormat = "0.0%";
dashboard.getRange("A10:D13").format.borders = { preset: "inside", style: "thin", color: "#E2E8F0" };

dashboard.getRange("F9:H9").merge();
dashboard.getRange("F9").values = [["本次 AI 成本"]];
dashboard.getRange("F9:H9").format = { fill: navy, font: { bold: true, color: "#FFFFFF" } };
dashboard.getRange("F10:G12").values = [["预计成本 USD", metrics.estimated_cost_usd || ""], ["实际成本 USD", metrics.actual_cost_usd || ""], ["Prompt 版本", run.prompt_version || ""]];
dashboard.getRange("F10:F12").format.font = { bold: true, color: "#475569" };
dashboard.getRange("F10:G12").format.borders = { preset: "inside", style: "thin", color: "#E2E8F0" };

const headers = ["客户名称", "客户ID", "成交意向分", "意向等级", "最近联系", "明确需求", "阻碍因素", "联系方式", "建议动作", "建议联系话术", "证据", "输入Token", "输出Token", "实际成本USD"];
leads.getRangeByIndexes(0, 0, 1, headers.length).values = [headers];
const rows = snapshot.leads.map((item) => [
  item.display_name, item.customer_id, item.intent_score, item.intent_band, new Date(item.recent_contact_ts * 1000),
  item.need, item.obstacles, item.contact, item.suggested_action, item.draft_text,
  item.evidence.map((evidence) => `${evidence.time} [${evidence.direction}] ${evidence.content}`).join("\n"),
  item.prompt_tokens, item.completion_tokens, Number(item.actual_cost_usd),
]);
leads.getRangeByIndexes(1, 0, rows.length, headers.length).values = rows;
const lastRow = rows.length + 1;
const table = leads.tables.add(`A1:N${lastRow}`, true, "LeadActivationTable");
table.style = "TableStyleMedium2";
table.showFilterButton = true;
table.showBandedRows = true;
leads.freezePanes.freezeRows(1);
leads.freezePanes.freezeColumns(2);
leads.getRange(`A1:N1`).format = { fill: navy, font: { bold: true, color: "#FFFFFF" }, rowHeight: 30 };
leads.getRange(`C2:C${lastRow}`).format.numberFormat = "0";
leads.getRange(`E2:E${lastRow}`).format.numberFormat = "yyyy-mm-dd hh:mm";
leads.getRange(`L2:M${lastRow}`).format.numberFormat = "#,##0";
leads.getRange(`N2:N${lastRow}`).format.numberFormat = "$0.000000";
leads.getRange(`F2:K${lastRow}`).format.wrapText = true;
leads.getRange(`D2:D${lastRow}`).conditionalFormats.add("containsText", { text: "高意向", format: { fill: "#DCFCE7", font: { color: green, bold: true } } });
leads.getRange(`D2:D${lastRow}`).conditionalFormats.add("containsText", { text: "待激活", format: { fill: "#FEF3C7", font: { color: amber, bold: true } } });
leads.getRange(`D2:D${lastRow}`).conditionalFormats.add("containsText", { text: "排除", format: { fill: "#FEE2E2", font: { color: red } } });
const widths = [16, 22, 12, 12, 19, 24, 24, 20, 30, 42, 54, 12, 12, 16];
widths.forEach((width, index) => { leads.getRangeByIndexes(0, index, lastRow, 1).format.columnWidth = width; });
leads.getRange(`A2:N${lastRow}`).format.rowHeight = 42;
dashboard.getRange("A1:H14").format.font.name = "PingFang SC";
dashboard.getRange("A1:H14").format.columnWidth = 16;
leads.getRange(`A1:N${lastRow}`).format.font.name = "PingFang SC";

const outputDir = outputPath.slice(0, outputPath.lastIndexOf("/"));
if (outputDir) await fs.mkdir(outputDir, { recursive: true });

await workbook.recalculate();
const dashboardCheck = await workbook.inspect({ kind: "table", range: "分析概览!A1:H13", include: "values,formulas", tableMaxRows: 13, tableMaxCols: 8 });
const errorCheck = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" });
if (formulaErrors.some((error) => errorCheck.ndjson.includes(error))) {
  throw new Error("WORKBOOK_FORMULA_ERROR");
}
if (process.env.PHASE4_VERIFY_DIR) {
  await fs.mkdir(process.env.PHASE4_VERIFY_DIR, { recursive: true });
  const dashboardPreview = await workbook.render({ sheetName: "分析概览", range: "A1:H14", scale: 1.5, format: "png" });
  await fs.writeFile(`${process.env.PHASE4_VERIFY_DIR}/dashboard.png`, new Uint8Array(await dashboardPreview.arrayBuffer()));
  const leadsPreview = await workbook.render({ sheetName: "客户激活表", range: `A1:N${Math.min(lastRow, 6)}`, scale: 1, format: "png" });
  await fs.writeFile(`${process.env.PHASE4_VERIFY_DIR}/leads.png`, new Uint8Array(await leadsPreview.arrayBuffer()));
  await fs.writeFile(`${process.env.PHASE4_VERIFY_DIR}/inspect.ndjson`, `${dashboardCheck.ndjson}\n${errorCheck.ndjson}\n`);
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
await fs.rm(`${outputPath}.inspect.ndjson`, { force: true });

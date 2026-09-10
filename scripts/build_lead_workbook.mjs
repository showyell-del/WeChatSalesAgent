import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [snapshotPath, outputPath] = process.argv.slice(2);
if (!snapshotPath || !outputPath) {
  throw new Error("usage: build_lead_workbook.mjs <snapshot.json> <output.xlsx>");
}

const snapshot = JSON.parse(await fs.readFile(snapshotPath, "utf8"));
const isPublishedAnalysis = snapshot.schema_version === "workspace.v2";
const isAgentQuery = snapshot.schema_version === "agent.query.v1";
if ((!isPublishedAnalysis && !isAgentQuery) || !Array.isArray(snapshot.leads) || snapshot.leads.length === 0) {
  throw new Error("LEAD_RESULT_SNAPSHOT_REQUIRED");
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
const formulaErrors = ["#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A"];
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

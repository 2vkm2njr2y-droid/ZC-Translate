# 准确率评测

- 模型档位：balanced
- 设备：NPU
- 数据集：`tests/fixtures/golden`
- 说明：chrF++ 只反映字面/字符相似度，最终以人工复核为准。

| 方向 | 句数 | chrF++ |
|---|---:|---:|
| zh-ja | 8 | 53.22 |
| zh-en | 8 | 79.28 |
| ja-zh | 8 | 46.46 |
| ja-en | 8 | 66.15 |
| en-zh | 8 | 52.46 |
| en-ja | 8 | 49.67 |

## 抽样

### zh-ja
- 原文：今天天气真好。我们下午去公园散步吧。
  - 参考：今日はとてもいい天気ですね。午後は公園へ散歩に行きましょう。
  - 译文：今日の天気は本当に素晴らしいです。午後にお公園に散策に行きましょう。
- 原文：会议资料昨天已经发送给所有参会者。
  - 参考：会議資料は昨日、全ての参加者に送付済みです。
  - 译文：会議資料は昨日、全参加者に送られました。
- 原文：这个版本修复了缓存目录缺失时的崩溃问题。
  - 参考：このバージョンは、キャッシュディレクトリがない場合のクラッシュを修正しました。
  - 译文：このバージョンは、キャッシュディレクションが欠落した際のクラッシュ問題を解決しました。
- 原文：请在下周一之前提交报销申请。
  - 参考：来週の月曜日までに経費精算の申請を提出してください。
  - 译文：月曜日までに申請書を提出してください。
- 原文：由于台风影响，明天的航班可能延误。
  - 参考：台風の影響で、明日の便が遅れる可能性があります。
  - 译文：台風の影響で、明日のフライトが遅延する可能性があります。

### zh-en
- 原文：今天天气真好。我们下午去公园散步吧。
  - 参考：The weather is really nice today. Let's take a walk in the park this afternoon.
  - 译文：The weather is really nice today. Let’s go for a walk in the park this afternoon.
- 原文：会议资料昨天已经发送给所有参会者。
  - 参考：The meeting materials were sent to all participants yesterday.
  - 译文：The conference materials were sent to all participants yesterday.
- 原文：这个版本修复了缓存目录缺失时的崩溃问题。
  - 参考：This version fixes a crash that occurred when the cache directory was missing.
  - 译文：This version fixes the crash issue when the cache directory is missing.
- 原文：请在下周一之前提交报销申请。
  - 参考：Please submit your reimbursement request by next Monday.
  - 译文：Please submit the reimbursement application by next Monday.
- 原文：由于台风影响，明天的航班可能延误。
  - 参考：Flights tomorrow may be delayed due to the typhoon.
  - 译文：Due to the typhoon, flights tomorrow may be delayed.

### ja-zh
- 原文：会議の資料は昨日のうちに全員に送っておきました。
  - 参考：会议资料昨天已经发送给所有人了。
  - 译文：会议资料已经于昨天将全部发给了每个人。
- 原文：今日はとても良い天気ですね。午後は公園を散歩しましょう。
  - 参考：今天天气真好。下午去公园散步吧。
  - 译文：今天天气非常好呢。下午我们去公园散步吧。
- 原文：このバージョンでは、キャッシュディレクトリがない場合のクラッシュを修正しました。
  - 参考：这个版本修复了缓存目录缺失时的崩溃问题。
  - 译文：在这个版本中，修复了在缓存目录不存在时的崩溃问题。
- 原文：来週の月曜日までに経費精算の申請を提出してください。
  - 参考：请在下周一之前提交报销申请。
  - 译文：请在下周周一之前提交费用报销申请。
- 原文：台風の影響で、明日の便が遅れる可能性があります。
  - 参考：受台风影响，明天的航班可能延误。
  - 译文：由于台风的影响，明天出行可能会延迟。

### ja-en
- 原文：会議の資料は昨日のうちに全員に送っておきました。
  - 参考：The meeting materials were sent to everyone by yesterday.
  - 译文：The meeting materials have been sent to everyone by yesterday.
- 原文：今日はとても良い天気ですね。午後は公園を散歩しましょう。
  - 参考：The weather is really nice today. Let's take a walk in the park this afternoon.
  - 译文：Today is really nice weather. Let’s go for a walk in the park afternoon.
- 原文：このバージョンでは、キャッシュディレクトリがない場合のクラッシュを修正しました。
  - 参考：This version fixes a crash that occurred when the cache directory was missing.
  - 译文：In this version, the crash when the cache directory is missing has been fixed.
- 原文：来週の月曜日までに経費精算の申請を提出してください。
  - 参考：Please submit your reimbursement request by next Monday.
  - 译文：Please submit the expense reimbursement request by Monday of next week.
- 原文：台風の影響で、明日の便が遅れる可能性があります。
  - 参考：Flights tomorrow may be delayed due to the typhoon.
  - 译文：Due to the typhoon, there may be a possibility that tomorrow’s travel will be delayed.

### en-zh
- 原文：The update fixes a crash when the cache directory is missing.
  - 参考：更新修复了缓存目录缺失时的崩溃问题。
  - 译文：更新后解决了缓存目录缺失时的崩溃问题。
- 原文：Please submit your expense report by next Monday.
  - 参考：请在下周一之前提交报销单。
  - 译文：请在下周一之前提交你的费用报告。
- 原文：The weather is lovely today. Let's take a walk in the park this afternoon.
  - 参考：今天天气真好。我们下午去公园散步吧。
  - 译文：今天天气很美好。今天下午我们去公园散步吧。
- 原文：The meeting materials were sent to all participants yesterday.
  - 参考：会议资料昨天已经发送给所有参会者。
  - 译文：会议材料昨天被发送给了所有参会者。
- 原文：Flights tomorrow may be delayed because of the typhoon.
  - 参考：受台风影响，明天的航班可能延误。
  - 译文：由于台风影响，明天的航班可能会推迟。

### en-ja
- 原文：The update fixes a crash when the cache directory is missing.
  - 参考：このアップデートは、キャッシュディレクトリがない場合のクラッシュを修正します。
  - 译文：この更新では、キャッチディレクタが欠落している際のクラッシュを解消しています。
- 原文：Please submit your expense report by next Monday.
  - 参考：来週の月曜日までに経費精算書を提出してください。
  - 译文：次の月曜日までに、費用報告書を提出してください。
- 原文：The weather is lovely today. Let's take a walk in the park this afternoon.
  - 参考：今日はとてもいい天気ですね。午後は公園を散歩しましょう。
  - 译文：今日の天気は素敵です。今日の午後、公園で散歩に行きましょう。
- 原文：The meeting materials were sent to all participants yesterday.
  - 参考：会議資料は昨日、全ての参加者に送付されました。
  - 译文：会議資料は昨日、全参加者に送られました。
- 原文：Flights tomorrow may be delayed because of the typhoon.
  - 参考：台風の影響で、明日の便が遅れる可能性があります。
  - 译文：明日の便は台風の影響で遅れる可能性があります。


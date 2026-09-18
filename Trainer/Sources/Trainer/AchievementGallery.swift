import SwiftUI

struct AchievementGallery: View {
    let items: [LearnerAchievement]
    @State private var filter = "全部"
    @State private var page = 0
    private let pageSize = 8
    private var filtered: [LearnerAchievement] {
        items.filter { filter == "全部" || (filter == "已解锁" ? $0.unlocked : !$0.unlocked) }
    }
    private var pages: Int { max(1, (filtered.count + pageSize - 1) / pageSize) }
    private var currentPage: Int { min(page, pages - 1) }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                VStack(alignment: .leading, spacing: 5) {
                    Label("学习成就", systemImage: "medal").font(.headline)
                    Text("已解锁 \(items.filter(\.unlocked).count) / \(items.count) · 学习足迹，不是能力认证")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Picker("筛选", selection: $filter) {
                    ForEach(["全部", "已解锁", "未解锁"], id: \.self) { Text($0) }
                }.labelsHidden().frame(width: 115)
            }
            if filtered.isEmpty { Text("这个分类还没有成就。完成一次练习记录，开启第一步。").foregroundStyle(.secondary).padding(.vertical, 24) }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 12)], spacing: 12) {
                ForEach(Array(filtered.dropFirst(currentPage * pageSize).prefix(pageSize)), id: \.title) { item in
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(spacing: 10) {
                            Image(systemName: item.icon ?? "medal").font(.title3)
                                .foregroundStyle(item.unlocked ? Color.cyan : Color.secondary)
                                .frame(width: 34, height: 34).background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
                            Text(item.title).font(.subheadline.weight(.semibold)).lineLimit(2)
                            Spacer(minLength: 0)
                            if item.unlocked { Image(systemName: "checkmark.seal.fill").foregroundStyle(.cyan) }
                        }
                        Text(item.detail ?? "继续记录学习足迹").font(.caption).foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, minHeight: 34, alignment: .topLeading)
                        FluidBar(value: Double(item.current ?? 0) / Double(max(1, item.target ?? 1)))
                        Text(item.unlocked ? "已解锁" : "\(item.current ?? 0) / \(item.target ?? 1)")
                            .font(.caption).monospacedDigit().foregroundStyle(.secondary)
                    }.padding(16).background(.black.opacity(0.12), in: RoundedRectangle(cornerRadius: 14))
                }
            }
            HStack {
                Text("共 \(filtered.count) 项 · 每页 \(pageSize) 项").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("上一页") { page = currentPage - 1 }.disabled(currentPage == 0)
                Text("\(currentPage + 1) / \(pages)").font(.caption).monospacedDigit().frame(minWidth: 45)
                Button("下一页") { page = currentPage + 1 }.disabled(currentPage + 1 >= pages)
            }
        }.onChange(of: filter) { _, _ in page = 0 }
    }
}

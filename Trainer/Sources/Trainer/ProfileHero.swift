import SwiftUI

/// Full-bleed cover with identity overlaid; no split surface or crossing avatar.
struct ProfileHero: View {
    let profile: LearnerProfile
    let cover: String
    let edit: () -> Void
    let chooseCover: () -> Void
    let resetCover: () -> Void

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            ProfileCover(reference: cover)
                .overlay(alignment: .topTrailing) {
                    Menu {
                        Button("编辑资料", systemImage: "pencil") { edit() }
                        Divider()
                        Button("更换封面", systemImage: "photo") { chooseCover() }
                        Button("恢复默认封面", systemImage: "arrow.counterclockwise") { resetCover() }
                    } label: {
                        Image(systemName: "ellipsis").font(.system(size: 18, weight: .medium))
                            .foregroundStyle(.white).frame(width: 36, height: 32)
                            .background(.black.opacity(0.20), in: Capsule())
                    }.menuStyle(.borderlessButton).fixedSize()
                        .help("管理个人资料与封面").accessibilityLabel("管理个人资料与封面")
                        .padding(20)
                }
            HStack(alignment: .center, spacing: 20) {
                ProfileAvatar(value: profile.avatar, size: 78)
                    .padding(3).background(.white.opacity(0.15), in: Circle())
                    .shadow(color: .black.opacity(0.18), radius: 12, y: 4)
                VStack(alignment: .leading, spacing: 6) {
                    Text(profile.name).font(.system(size: 28, weight: .semibold))
                        .tracking(-0.6).lineLimit(1).foregroundStyle(.white)
                    Text(profile.bio.isEmpty ? "保持好奇，持续生长。" : profile.bio)
                        .font(.callout).foregroundStyle(.white.opacity(0.8)).lineLimit(2)
                }.frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "lock.shield").font(.system(size: 18, weight: .light))
                    .foregroundStyle(.white.opacity(0.65))
                    .help("个人资料与封面仅保存在本机")
                    .accessibilityLabel("个人资料与封面仅保存在本机")
            }.padding(28)
        }.frame(height: 220).clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}

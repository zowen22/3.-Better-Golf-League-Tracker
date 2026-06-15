import SwiftUI

struct RootView: View {
    @Environment(AuthViewModel.self) private var authVM

    var body: some View {
        if authVM.isAuthenticated {
            MainTabView()
        } else {
            LoginView()
        }
    }
}

import SwiftUI

struct LoginView: View {
    @Environment(AuthViewModel.self) private var authVM

    @State private var leagueCode = ""
    @State private var password = ""

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Spacer()

                Text("Golf League Tracker")
                    .font(.largeTitle.bold())

                VStack(spacing: 16) {
                    TextField("League Code", text: $leagueCode)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .textFieldStyle(.roundedBorder)

                    SecureField("Password", text: $password)
                        .textFieldStyle(.roundedBorder)
                }
                .padding(.horizontal)

                if let error = authVM.errorMessage {
                    Text(error)
                        .foregroundStyle(.red)
                        .font(.footnote)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                }

                Button {
                    Task { await authVM.login(email: "", password: password, leagueCode: leagueCode) }
                } label: {
                    if authVM.isLoading {
                        ProgressView()
                            .frame(maxWidth: .infinity)
                    } else {
                        Text("Sign In")
                            .frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(authVM.isLoading)
                .padding(.horizontal)

                Spacer()
            }
            .navigationBarHidden(true)
        }
    }
}
